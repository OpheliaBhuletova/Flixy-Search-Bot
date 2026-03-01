from pyrogram.types import Message
from pyrogram import enums
from typing import Union


def get_size(size: int | float) -> str:
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB"]
    size = float(size)
    index = 0

    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    return f"{size:.2f} {units[index]}"


def split_list(data: list, size: int):
    for i in range(0, len(data), size):
        yield data[i:i + size]


def get_file_id(message: Message):
    if not message.media:
        return None

    for media_type in (
        "photo", "animation", "audio", "document",
        "video", "video_note", "voice", "sticker"
    ):
        media = getattr(message, media_type, None)
        if media:
            setattr(media, "message_type", media_type)
            return media


def extract_user(message: Message) -> tuple[Union[int, str], str]:
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        return user.id, user.first_name

    if len(message.command) > 1:
        entity = message.entities[1] if message.entities else None
        if entity and entity.type == enums.MessageEntityType.TEXT_MENTION:
            user = entity.user
            return user.id, user.first_name
        try:
            return int(message.command[1]), message.command[1]
        except ValueError:
            return message.command[1], message.command[1]

    return message.from_user.id, message.from_user.first_name


def last_online(user) -> str:
    if user.is_bot:
        return "🤖 Bot"

    status_map = {
        enums.UserStatus.RECENTLY: "Recently",
        enums.UserStatus.LAST_WEEK: "Within the last week",
        enums.UserStatus.LAST_MONTH: "Within the last month",
        enums.UserStatus.LONG_AGO: "A long time ago",
        enums.UserStatus.ONLINE: "Currently Online",
    }

    if user.status in status_map:
        return status_map[user.status]

    if user.status == enums.UserStatus.OFFLINE:
        return user.last_online_date.strftime("%d %b %Y, %H:%M")

    return "Unknown"

from pyrogram.errors import UserNotParticipant

async def is_subscribed(client, query) -> bool:
    if not query.message or not query.from_user:
        return True

    try:
        await client.get_chat_member(
            query.message.chat.id,
            query.from_user.id
        )
        return True
    except UserNotParticipant:
        return False
    except Exception:
        return True


def is_sudo(user_id: int) -> bool:
    """Return ``True`` if the given user is listed in ``settings.SUDO_USERS``.

    Sudo users bypass various restrictions (subscription checks, bans,
    etc.) so they can always receive PM movie responses regardless of
    the normal authorization state.
    """
    try:
        return user_id in settings.SUDO_USERS
    except Exception:
        # if settings not yet imported or list misconfigured, be safe
        return False

from database.users_chats_db import get_db_instance

async def get_settings(chat_id: int):
    db = get_db_instance()
    return await db.get_settings(chat_id)

async def save_group_settings(chat_id: int, settings: dict):
    db = get_db_instance()
    await db.update_settings(chat_id, settings)


import asyncio
import logging

logger = logging.getLogger(__name__)


def schedule_delete_message(client, chat_id: int, message_id: int, delay_seconds: int = 6 * 3600):
    """Schedule deletion of a message after delay_seconds in background.

    Non-blocking: creates an asyncio task to sleep then delete the message.
    """

    async def _del():
        try:
            await asyncio.sleep(delay_seconds)
            await client.delete_messages(chat_id, message_id)
        except Exception as e:
            logger.debug("Could not auto-delete message %s in %s: %s", message_id, chat_id, e)

    try:
        asyncio.create_task(_del())
    except RuntimeError:
        # If there's no running loop, just ignore scheduling
        logger.debug("Event loop not running; cannot schedule deletion for %s", message_id)