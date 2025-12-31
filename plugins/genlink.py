import re
import os
import json
import base64
import logging

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid,
    UsernameInvalid,
    UsernameNotModified,
)

from bot.config import settings
from bot.utils.cache import RuntimeCache
from bot.database.ia_filterdb import unpack_new_file_id

logger = logging.getLogger(__name__)


async def allowed(_, __, message: Message) -> bool:
    if settings.PUBLIC_FILE_STORE:
        return True
    if message.from_user and message.from_user.id in settings.ADMINS:
        return True
    return False


@Client.on_message(filters.command(["link", "plink"]) & filters.create(allowed))
async def generate_link_handler(client: Client, message: Message):
    replied = message.reply_to_message
    if not replied:
        return await message.reply("Reply to a message to get a shareable link.")

    media_type = replied.media
    if media_type not in {
        enums.MessageMediaType.VIDEO,
        enums.MessageMediaType.AUDIO,
        enums.MessageMediaType.DOCUMENT,
    }:
        return await message.reply("Reply to a supported media file.")

    if message.has_protected_content and message.from_user.id not in settings.ADMINS:
        return await message.reply("You are not authorized to generate this link.")

    media = getattr(replied, media_type.value)
    file_id, _ = unpack_new_file_id(media.file_id)

    prefix = "filep_" if message.command[0] == "plink" else "file_"
    encoded = base64.urlsafe_b64encode(
        f"{prefix}{file_id}".encode("ascii")
    ).decode().strip("=")

    await message.reply(
        f"Here is your link:\n"
        f"https://t.me/{RuntimeCache.bot_username}?start={encoded}"
    )


@Client.on_message(filters.command(["batch", "pbatch"]) & filters.create(allowed))
async def generate_batch_link_handler(client: Client, message: Message):
    parts = message.text.split()
    if len(parts) != 3:
        return await message.reply("Use correct format.")

    cmd, first, last = parts
    regex = re.compile(
        r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[\w_]+)/(\d+)$"
    )

    match_f = regex.match(first)
    match_l = regex.match(last)
    if not match_f or not match_l:
        return await message.reply("Invalid link.")

    f_chat_id, f_msg_id = match_f.group(4), int(match_f.group(5))
    l_chat_id, l_msg_id = match_l.group(4), int(match_l.group(5))

    if f_chat_id.isnumeric():
        f_chat_id = int("-100" + f_chat_id)
    if l_chat_id.isnumeric():
        l_chat_id = int("-100" + l_chat_id)

    if f_chat_id != l_chat_id:
        return await message.reply("Chat IDs do not match.")

    try:
        chat_id = (await client.get_chat(f_chat_id)).id
    except ChannelInvalid:
        return await message.reply(
            "Private channel/group. Make me admin to proceed."
        )
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply("Invalid link specified.")
    except Exception as e:
        return await message.reply(f"Error: {e}")

    status = await message.reply(
        "Generating link...\nThis may take time depending on messages."
    )

    if chat_id in settings.FILE_STORE_CHANNEL:
        payload = f"{f_msg_id}_{l_msg_id}_{chat_id}_{cmd.lower()}"
        encoded = base64.urlsafe_b64encode(
            payload.encode("ascii")
        ).decode().strip("=")
        return await status.edit(
            f"Here is your link:\n"
            f"https://t.me/{RuntimeCache.bot_username}?start=DSTORE-{encoded}"
        )

    out = []
    count = 0

    async for msg in client.iter_messages(f_chat_id, l_msg_id, f_msg_id):
        if not msg.media or msg.empty or msg.service:
            continue

        media = getattr(msg, msg.media.value)
        if not media:
            continue

        out.append(
            {
                "file_id": media.file_id,
                "caption": msg.caption.html if msg.caption else "",
                "title": getattr(media, "file_name", ""),
                "size": media.file_size,
                "protect": cmd.lower() == "pbatch",
            }
        )
        count += 1

    filename = f"batch_{message.from_user.id}.json"
    with open(filename, "w") as f:
        json.dump(out, f)

    post = await client.send_document(
        settings.LOG_CHANNEL,
        filename,
        caption="Generated batch file for filestore.",
    )
    os.remove(filename)

    batch_file_id, _ = unpack_new_file_id(post.document.file_id)
    await status.edit(
        f"Here is your link\n"
        f"Contains `{count}` files.\n"
        f"https://t.me/{RuntimeCache.bot_username}?start=BATCH-{batch_file_id}"
    )