import asyncio
import logging
from typing import Union, Optional
import re

from pyrogram import enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.errors import UserNotParticipant

from bot.config import settings
from database.users_chats_db import get_db_instance

logger = logging.getLogger(__name__)


def build_button(
    text: str,
    callback_data: str | None = None,
    url: str | None = None,
    style: enums.ButtonStyle | None = None,
    switch_inline_query_current_chat: str | None = None,
) -> InlineKeyboardButton:
    """Create an inline button while keeping the common kwargs centralized."""
    kwargs = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if switch_inline_query_current_chat is not None:
        kwargs["switch_inline_query_current_chat"] = switch_inline_query_current_chat
    if style is not None:
        kwargs["style"] = style
    return InlineKeyboardButton(text, **kwargs)


def build_inline_markup(buttons: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    """Wrap a button matrix into an InlineKeyboardMarkup object."""
    if buttons is None:
        buttons = []
    return InlineKeyboardMarkup(buttons)


def build_support_button_row(support_chat: str | None = None) -> list[list[InlineKeyboardButton]]:
    """Build the common support button row for restricted or leave notifications."""
    chat = support_chat or getattr(settings, "SUPPORT_CHAT", "")
    if chat:
        return [[build_button("Support", url=f"https://t.me/{chat}", style=enums.ButtonStyle.SUCCESS)]]
    return [[build_button("Support", callback_data="close_data", style=enums.ButtonStyle.SUCCESS)]]


def build_cancel_button_row(callback_data: str = "index_cancel") -> list[list[InlineKeyboardButton]]:
    """Build a single cancel button row for index operations."""
    return [[build_button("Cancel", callback_data=callback_data, style=enums.ButtonStyle.DANGER)]]


def build_close_button_row(back_callback: str = "start") -> list[InlineKeyboardButton]:
    """Build a typical back/close row used across help/about menus."""
    return [
        build_button("◀️ Back", callback_data=back_callback, style=enums.ButtonStyle.PRIMARY),
        build_button("❌ Close", callback_data="close_data", style=enums.ButtonStyle.DANGER),
    ]


def build_start_buttons() -> list[list[InlineKeyboardButton]]:
    """Build the common start menu with search and watchlist actions."""
    return [
        [
            build_button("🔍 Search", switch_inline_query_current_chat="", style=enums.ButtonStyle.SUCCESS),
            build_button("👀 Watchlist", callback_data="mywatchlist_start", style=enums.ButtonStyle.PRIMARY),
        ],
        [
            build_button("ℹ️ About", callback_data="about", style=enums.ButtonStyle.PRIMARY),
            build_button("📖 Help", callback_data="help", style=enums.ButtonStyle.DANGER),
        ],
    ]


def get_size(size: int | float) -> str:
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB"]
    size = float(size)
    index = 0

    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    return f"{size:.2f} {units[index]}"


def remove_file_extension(filename: str) -> str:
    """Remove file extension from filename.
    
    Examples:
        "Movie.mkv" -> "Movie"
        "Series S01E01.mp4" -> "Series S01E01"
    """
    if not filename:
        return filename
    return re.sub(r"\.[^.]+$", "", filename)


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


async def get_settings(chat_id: int):
    db = get_db_instance()
    return await db.get_settings(chat_id)

async def save_group_settings(chat_id: int, settings: dict):
    db = get_db_instance()
    await db.update_settings(chat_id, settings)


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


def extract_series_name_from_file(file_name: str, caption: Optional[str] = None) -> Optional[str]:
    """Extract TV series name from file name or caption.
    
    Supports formats like:
    - "Series Name S01E01.mkv"
    - "Series.Name.S01E01.mkv"
    - "Series Name - Season 01 Episode 01.mkv"
    - Caption might contain series name
    
    Returns the series name without episode info, or None if not found.
    """
    # Try caption first if available
    if caption:
        # Caption might contain series info in HTML format
        text = caption.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        # Extract just the first line which often has the series name
        first_line = text.split("\n")[0].strip()
        if first_line and len(first_line) > 2:
            return first_line
    
    if not file_name:
        return None
    
    # Remove file extension
    name_without_ext = re.sub(r"\.[^.]+$", "", file_name)
    
    # Pattern: Look for S##E## (season/episode marker) and extract everything before it
    # This handles both "Series.Name.S01E01" and "Series Name S01E01"
    match = re.search(r"^(.+?)[\s\.]*[Ss]\d{1,2}[Ee]\d{1,2}", name_without_ext)
    if match:
        series_name = match.group(1).strip()
        # Replace dots and extra spaces with single spaces
        series_name = re.sub(r"[\.\s]+", " ", series_name).strip()
        if series_name and len(series_name) > 1:
            return series_name
    
    # Pattern: "Series Name - Season xx Episode xx"
    match = re.search(r"^(.+?)\s*-\s*Season\s+\d+\s+Episode\s+\d+", name_without_ext, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Pattern: "Series Name Season xx Episode xx"
    match = re.search(r"^(.+?)\s+Season\s+\d+\s+Episode\s+\d+", name_without_ext, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    return None