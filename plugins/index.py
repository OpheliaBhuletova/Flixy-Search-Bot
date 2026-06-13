import re
import time
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
from database.ia_filterdb import save_file, save_file_inline, save_file_pm, announce_title
from bot.utils.broadcast import new_movie_broadcast

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

    parts = query.data.split("#")
    
    if parts[1] == "reject":
        _, action, chat, last_msg_id, from_user = parts
        await query.message.delete()
        await client.send_message(
            int(from_user),
            f"Your submission for indexing `{chat}` was rejected by moderators.",
            reply_to_message_id=int(last_msg_id),
        )
        return

    if parts[1] == "db_select":
        # Database selection callback
        _, action, db_type, chat, last_msg_id, from_user = parts
        
        if lock.locked():
            return await query.answer(
                "Please wait until the previous indexing finishes.",
                show_alert=True,
            )
        
        await query.answer(f"Indexing to {db_type.upper()} database... ⏳", show_alert=True)
        
        await query.message.edit(
            f"Starting indexing to {db_type.upper()} database...",
            reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Cancel", callback_data="index_cancel", style=enums.ButtonStyle.DANGER)]]))
        
        try:
            chat = int(chat)
        except ValueError:
            pass
        
        await index_files_to_db(
            client,
            chat,
            int(last_msg_id),
            query.message,
            db_type=db_type,
        )
        return
    
    # Accept callback - ask for database selection
    _, action, chat, last_msg_id, from_user = parts[:5]
    
    if action != "accept":
        return

    if lock.locked():
        return await query.answer(
            "Please wait until the previous indexing finishes.",
            show_alert=True,
        )

    if int(from_user) not in settings.ADMINS:
        await client.send_message(
            int(from_user),
            f"Your submission for indexing `{chat}` was approved and will be processed soon.",
            reply_to_message_id=int(last_msg_id),
        )
    
    # Ask for database selection
    if True:  # Hardcoded: Multi-DB enabled
        await query.answer()
        db_buttons = [
            [
                InlineKeyboardButton(
                    "📌 Inline DB",
                    callback_data=f"index#db_select#inline#{chat}#{last_msg_id}#{from_user}",
                    style=enums.ButtonStyle.PRIMARY,
                )
            ],
            [
                InlineKeyboardButton(
                    "💬 PM DB",
                    callback_data=f"index#db_select#pm#{chat}#{last_msg_id}#{from_user}",
                    style=enums.ButtonStyle.PRIMARY,
                )
            ],
        ]
        return await query.message.edit(
            f"Select target database for indexing `{chat}`:",
            reply_markup=InlineKeyboardMarkup(db_buttons),
        )
    else:
        # Multi-DB disabled, proceed with default
        await query.answer("Processing... ⏳", show_alert=True)
        await query.message.edit(
            "Starting indexing...",
            reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Cancel", callback_data="index_cancel", style=enums.ButtonStyle.DANGER)]]))
        try:
            chat = int(chat)
        except ValueError:
            pass
        
        await index_files_to_db(
            client,
            chat,
            int(last_msg_id),
            query.message,
            db_type="default",
        )


# ─── SEND INDEX REQUEST ───────────────────────────────────────────────

@Client.on_message(
    filters.forwarded & filters.private
)
async def send_for_index(client: Client, message: Message):
    if not message.forward_from_chat or message.forward_from_chat.type != enums.ChatType.CHANNEL:
        return
    
    chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    last_msg_id = message.forward_from_message_id

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
                    style=enums.ButtonStyle.PRIMARY,
                )
            ],
            [InlineKeyboardButton("Close", callback_data="close_data", style=enums.ButtonStyle.DANGER)],
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
                style=enums.ButtonStyle.SUCCESS,
            )
        ],
        [
            InlineKeyboardButton(
                "Reject Index",
                callback_data=f"index#reject#{chat_id}#{message.id}#{message.from_user.id}",
                style=enums.ButtonStyle.DANGER,
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
    db_type: str = "default",
):
    total = duplicate = errors = deleted = no_media = unsupported = 0
    start_time = time.time()

    def build_progress_bar(current_value: int, total_value: int, length: int = 10) -> str:
        if total_value <= 0:
            return "□□□□□□□□□□"
        filled = min(length, int((current_value / total_value) * length))
        return "■" * filled + "□" * (length - filled)

    def format_eta(seconds: float) -> str:
        if seconds <= 0:
            return "0s"
        if seconds < 60:
            return f"{int(seconds)}s"
        minutes, sec = divmod(int(seconds), 60)
        return f"{minutes}m {sec}s"

    async with lock:
        RuntimeCache.cancel_index = False
        current = RuntimeCache.index_skip
        total_target = max(last_msg_id - RuntimeCache.index_skip, 0)

        # Bots cannot iterate history; we crawl backwards using message IDs instead
        for i in range(0, total_target, 150):
            if RuntimeCache.cancel_index:
                break
            
            try:
                # Generate a batch of IDs to fetch (descending)
                batch_ids = [last_msg_id - j for j in range(i, min(i + 150, total_target))]
                messages = await client.get_messages(chat_id, batch_ids)

                for msg in messages:
                    if RuntimeCache.cancel_index:
                        break

                    current += 1

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

                    # Skip .txt files
                    if hasattr(media, 'file_name') and media.file_name and media.file_name.endswith('.txt'):
                        logger.info(f"⏭️ Skipping .txt file during indexing: {media.file_name}")
                        unsupported += 1
                        continue

                    media.file_type = msg.media.value
                    media.caption = msg.caption

                    saved, reason, title = await save_file(media, db_type=db_type)

                    if saved:
                        total += 1
                        # Mark as announced regardless of DB to prevent future broadcast spam
                        await announce_title(title)
                    elif reason == 0:
                        duplicate += 1
                    else:
                        errors += 1

                # Add small delay after each batch to prevent rate limits
                await asyncio.sleep(0.25)

                # Update progress after each batch
                elapsed = round(time.time() - start_time, 2)
                processed = total + duplicate + deleted + no_media + unsupported + errors
                speed = round(processed / elapsed, 2) if elapsed > 0 else 0
                progress_percent = round((current / total_target) * 100, 1) if total_target > 0 else 0
                progress_bar = build_progress_bar(current, total_target)

                remaining_items = max(total_target - current, 0)
                eta_seconds = round(remaining_items / speed, 2) if speed > 0 else 0

                db_name = settings.DATABASE_NAME_INLINE if db_type == "inline" else settings.DATABASE_NAME_PM
                db_label = "📌 Inline DB" if db_type == "inline" else "💬 PM DB" if db_type == "pm" else "📦 Default DB"
                try:
                    await status_msg.edit_text(
                            f"📦 <b>Indexing in Progress</b> ({db_label})\n\n"
                            f"<code>{progress_bar}</code> <b>{progress_percent}%</b>\n\n"
                            "<b>Summary:</b>\n"
                            f"• 🗄 Database: <code>{db_name}</code>\n"
                            f"• 📥 Fetched: <code>{current}</code> / <code>{total_target}</code>\n"
                            f"• ✅ Saved: <code>{total}</code>\n"
                            f"• ♻️ Duplicates: <code>{duplicate}</code>\n"
                            f"• 🗑 Deleted: <code>{deleted}</code>\n"
                            f"• 📄 Non-media: <code>{no_media + unsupported}</code>\n"
                            f"• ⚠️ Errors: <code>{errors}</code>\n\n"
                            f"⏱ <b>Time:</b> <code>{elapsed}s</code>\n"
                            f"⚡ <b>Speed:</b> <code>{speed} files/sec</code>\n"
                            f"🕒 <b>ETA:</b> <code>{format_eta(eta_seconds)}</code>",
                            parse_mode=enums.ParseMode.HTML,
                            reply_markup=InlineKeyboardMarkup(
                                [[InlineKeyboardButton("Cancel", callback_data="index_cancel", style=enums.ButtonStyle.DANGER)]]
                            ),
                        )
                except Exception:
                    pass

            except FloodWait as e:
                wait_time = e.value + 2  # Add buffer to e.value
                logger.warning(f"FloodWait: Sleeping for {wait_time}s")
                await asyncio.sleep(wait_time)
            except Exception as e:
                logger.exception(f"Error during batch: {e}")
                errors += 1

        # Final stats reporting
        time_taken = round(time.time() - start_time, 2)
        processed_count = total + duplicate + deleted + no_media + unsupported + errors
        final_speed = round(processed_count / time_taken, 2) if time_taken > 0 else 0
        db_name = settings.DATABASE_NAME_INLINE if db_type == "inline" else settings.DATABASE_NAME_PM
        db_label = "📌 Inline DB" if db_type == "inline" else "💬 PM DB" if db_type == "pm" else "📦 Default DB"
        status_header = "❌ <b>Indexing Cancelled</b>" if RuntimeCache.cancel_index else "✅ <b>Indexing Complete</b>"
        
        await status_msg.edit_text(
            f"{status_header} ({db_label})\n\n"
            "<b>Summary:</b>\n"
            f"• 🗄 Database: <code>{db_name}</code>\n"
            f"• ✅ Saved: <code>{total}</code>\n"
            f"• ♻️ Duplicates: <code>{duplicate}</code>\n"
            f"• 🗑 Deleted: <code>{deleted}</code>\n"
            f"• 📄 Non-media: <code>{no_media + unsupported}</code>\n"
            f"• ⚠️ Errors: <code>{errors}</code>\n\n"
            f"⏱ <b>Time:</b> <code>{time_taken}s</code>\n"
            f"⚡ <b>Speed:</b> <code>{final_speed} files/sec</code>",
            parse_mode=enums.ParseMode.HTML,
        )