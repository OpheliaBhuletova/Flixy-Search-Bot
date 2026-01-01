import re
import asyncio
import logging

from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
)
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid,
    ChatAdminRequired,
    UsernameInvalid,
    UsernameNotModified,
)

from bot.config import settings
from bot.utils.cache import RuntimeCache
from database.ia_filterdb import save_file

logger = logging.getLogger(__name__)

lock = asyncio.Lock()

LINK_REGEX = re.compile(
    r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[\w_]+)/(\d+)$"
)


# ─── CALLBACK: ACCEPT / REJECT INDEX ──────────────────────────────────

@Client.on_callback_query(filters.regex(r"^index"))
async def index_callback_handler(client: Client, query: CallbackQuery):
    if query.data == "index_cancel":
        RuntimeCache.cancel_index = True
        return await query.answer("Cancelling indexing...")

    _, action, chat, last_msg_id, from_user = query.data.split("#")

    if action == "reject":
        await query.message.delete()
        await client.send_message(
            int(from_user),
            f"Your submission for indexing `{chat}` was rejected by moderators.",
            reply_to_message_id=int(last_msg_id),
        )
        return

    if lock.locked():
        return await query.answer(
            "Please wait until the previous indexing finishes.",
            show_alert=True,
        )

    await query.answer("Processing... ⏳", show_alert=True)

    if int(from_user) not in settings.ADMINS:
        await client.send_message(
            int(from_user),
            f"Your submission for indexing `{chat}` was approved and will be processed soon.",
            reply_to_message_id=int(last_msg_id),
        )

    await query.message.edit(
        "Starting indexing...",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Cancel", callback_data="index_cancel")]]
        ),
    )

    try:
        chat = int(chat)
    except ValueError:
        pass

    await index_files_to_db(
        client,
        chat,
        int(last_msg_id),
        query.message,
    )


# ─── SEND INDEX REQUEST ───────────────────────────────────────────────

@Client.on_message(
    (
        filters.forwarded
        | (filters.regex(LINK_REGEX.pattern) & filters.text)
    )
    & filters.private
)
async def send_for_index(client: Client, message: Message):
    if message.text:
        match = LINK_REGEX.match(message.text)
        if not match:
            return await message.reply("Invalid link.")

        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)

    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
        last_msg_id = message.forward_from_message_id
    else:
        return

    try:
        await client.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply(
            "Private channel/group. Make me admin there to index files."
        )
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply("Invalid link specified.")
    except Exception as e:
        logger.exception(e)
        return await message.reply(f"Error: {e}")

    try:
        last_msg = await client.get_messages(chat_id, last_msg_id)
    except Exception:
        return await message.reply(
            "Make sure I am admin in the channel/group."
        )

    if last_msg.empty:
        return await message.reply("I am not admin in this group.")

    # Admin direct approval
    if message.from_user.id in settings.ADMINS:
        buttons = [
            [
                InlineKeyboardButton(
                    "Yes",
                    callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}",
                )
            ],
            [InlineKeyboardButton("Close", callback_data="close_data")],
        ]
        return await message.reply(
            f"Do you want to index this chat?\n\n"
            f"Chat: <code>{chat_id}</code>\n"
            f"Last Message ID: <code>{last_msg_id}</code>",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    # Send to moderators
    if isinstance(chat_id, int):
        try:
            link = (await client.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply(
                "Make sure I have invite permissions."
            )
    else:
        link = f"@{chat_id}"

    buttons = [
        [
            InlineKeyboardButton(
                "Accept Index",
                callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}",
            )
        ],
        [
            InlineKeyboardButton(
                "Reject Index",
                callback_data=f"index#reject#{chat_id}#{message.id}#{message.from_user.id}",
            )
        ],
    ]

    await client.send_message(
        settings.INDEX_REQ_CHANNEL,
        f"#IndexRequest\n\n"
        f"By: {message.from_user.mention} (`{message.from_user.id}`)\n"
        f"Chat: <code>{chat_id}</code>\n"
        f"Last Message ID: <code>{last_msg_id}</code>\n"
        f"Invite: {link}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

    await message.reply(
        "Thank you for your contribution. Moderators will review it shortly."
    )


# ─── SET SKIP NUMBER ──────────────────────────────────────────────────

@Client.on_message(filters.command("setskip") & filters.user(settings.ADMINS))
async def set_skip_number(client: Client, message: Message):
    try:
        _, skip = message.text.split()
        RuntimeCache.index_skip = int(skip)
        await message.reply(f"Successfully set SKIP number to {skip}")
    except Exception:
        await message.reply("Usage: /setskip <number>")


# ─── CORE INDEXING FUNCTION ───────────────────────────────────────────

async def index_files_to_db(
    client: Client,
    chat_id: int,
    last_msg_id: int,
    status_msg: Message,
):
    total = duplicate = errors = deleted = no_media = unsupported = 0

    async with lock:
        RuntimeCache.cancel_index = False
        current = RuntimeCache.index_skip

        try:
            async for msg in client.iter_messages(chat_id, last_msg_id, current):
                if RuntimeCache.cancel_index:
                    break

                current += 1

                if current % 20 == 0:
                    await status_msg.edit(
                        f"Fetched: <code>{current}</code>\n"
                        f"Saved: <code>{total}</code>\n"
                        f"Duplicates: <code>{duplicate}</code>\n"
                        f"Deleted: <code>{deleted}</code>\n"
                        f"Non-media: <code>{no_media + unsupported}</code>\n"
                        f"Errors: <code>{errors}</code>",
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("Cancel", callback_data="index_cancel")]]
                        ),
                    )

                if msg.empty:
                    deleted += 1
                    continue

                if not msg.media:
                    no_media += 1
                    continue

                if msg.media not in {
                    enums.MessageMediaType.VIDEO,
                    enums.MessageMediaType.AUDIO,
                    enums.MessageMediaType.DOCUMENT,
                }:
                    unsupported += 1
                    continue

                media = getattr(msg, msg.media.value, None)
                if not media:
                    unsupported += 1
                    continue

                media.file_type = msg.media.value
                media.caption = msg.caption

                saved, reason = await save_file(media)
                if saved:
                    total += 1
                elif reason == 0:
                    duplicate += 1
                else:
                    errors += 1

        except FloodWait as e:
            await asyncio.sleep(e.x)
        except Exception as e:
            logger.exception(e)
            await status_msg.edit(f"Error: {e}")
        else:
            await status_msg.edit(
                f"Indexing complete!\n\n"
                f"Saved: <code>{total}</code>\n"
                f"Duplicates: <code>{duplicate}</code>\n"
                f"Deleted: <code>{deleted}</code>\n"
                f"Non-media: <code>{no_media + unsupported}</code>\n"
                f"Errors: <code>{errors}</code>"
            )