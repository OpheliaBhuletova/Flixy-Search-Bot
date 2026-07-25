import asyncio
import logging
import re
from pyrogram import Client, enums
from pyrogram.errors import (
    InputUserDeactivated,
    UserIsBlocked,
    PeerIdInvalid,
    FloodWait,
)
from pyrogram.types import Message, InlineKeyboardButton
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import build_inline_markup, schedule_delete_message
from bot.config import settings
from database.users_chats_db import db

logger = logging.getLogger(__name__)

def _split_title_year(title: str) -> tuple[str, str | None]:
    if not title:
        return "", None

    match = re.match(r"^(.*?)\s*\((\d{4})\)\s*$", title.strip())
    if match:
        return match.group(1).strip(), match.group(2)

    return title.strip(), None

def _detect_media_type(title: str) -> str:
    """Detect if title is a TV Series or Movie based on common patterns.
    
    Returns: "TV Series" or "Movie"
    """
    title_lower = title.lower()
    
    # TV Series indicators: Season numbers, episode numbers, series keywords
    tv_indicators = [
        r"\bs\d+e\d+\b",  # S01E01
        r"\bseason\s*\d+\b",  # Season 1
        r"\bepisode\s*\d+\b",  # Episode 1
        r"\bep\s*\d+\b",  # Ep 1
        r"\b\(\s*\d{4}\s*\)\s*(?:s|season|tv)",  # (2024) season/s
    ]
    
    for pattern in tv_indicators:
        if re.search(pattern, title_lower):
            return "TV Series"
    
    return "Movie"

async def broadcast_messages(user_id: int, message: Message):
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"

    except FloodWait as e:
        sleep_time = getattr(e, "x", None) or getattr(e, "value", None) or 0
        await asyncio.sleep(sleep_time)
        return await broadcast_messages(user_id, message)

    except InputUserDeactivated:
        await db.delete_user(user_id)
        logger.info("Removed deleted user %s", user_id)
        return False, "Deleted"

    except UserIsBlocked:
        logger.info("User %s blocked the bot", user_id)
        return False, "Blocked"

    except PeerIdInvalid:
        await db.delete_user(user_id)
        logger.info("PeerIdInvalid for %s", user_id)
        return False, "Error"

    except Exception as e:
        logger.exception(e)
        return False, "Error"

async def new_movie_broadcast(client: Client, title: str, message: Message = None):
    """Notify all users about a newly indexed movie/series title.
    
    Args:
        client: Pyrogram client
        title: Title of the movie/series
        message: Optional original message to forward to users instead of just sending text
    """
    users = await db.get_all_users()
    movie_title, movie_year = _split_title_year(title)
    media_type = _detect_media_type(title)
    display_name = f"{movie_title} ({movie_year})" if movie_year else movie_title
    
    # Format the notification message
    icon = "📺" if media_type == "TV Series" else "🎬"
    msg_text = (
        f"{icon} <b>New {media_type} Added</b>\n\n"
        f"<b>Title:</b> {movie_title}\n"
        f"<b>Year:</b> {movie_year or 'N/A'}\n"
        f"<b>Type:</b> {media_type}\n\n"
        "🔎 <b>Search instantly:</b>\n"
        f"Use inline search — <code>@{RuntimeCache.bot_username} {display_name}</code>\n\n"
        "📩 <b>Or send me the movie name in PM</b> to get the file."
    )

    buttons = [[
        InlineKeyboardButton(
            "🔎 Search Instantly",
            switch_inline_query_current_chat=title,
            style=enums.ButtonStyle.PRIMARY,
        )
    ]]

    total = await db.total_users_count()
    done = success = blocked = deleted = failed = 0

    async for user in users:
        uid = int(user["id"])
        try:
            if message:
                # Forward the original message from the channel
                await message.copy(chat_id=uid)
                success += 1
            else:
                # Fallback to sending text notification with search button
                await client.send_message(
                    uid,
                    msg_text,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=build_inline_markup(buttons),
                )
                success += 1
        except InputUserDeactivated:
            await db.delete_user(uid)
            deleted += 1
        except UserIsBlocked:
            blocked += 1
        except PeerIdInvalid:
            await db.delete_user(uid)
            failed += 1
        except Exception:
            logger.exception("Failed to send broadcast to %s", uid)
            failed += 1
        finally:
            done += 1
            await asyncio.sleep(1)

    log_channel = getattr(settings, "LOG_CHANNEL", 0)
    if log_channel:
        try:
            icon = "📺" if media_type == "TV Series" else "🎬"
            report = (
                f"{icon} <b>{media_type} Broadcast Report</b>\n\n"
                f"<b>Title:</b> <code>{title}</code>\n"
                f"<b>Total:</b> {total}\n"
                f"<b>Delivered:</b> {success}\n"
                f"<b>Blocked:</b> {blocked}\n"
                f"<b>Deleted:</b> {deleted}\n"
                f"<b>Failed:</b> {failed}"
            )
            msg = await client.send_message(
                log_channel,
                report,
                parse_mode=enums.ParseMode.HTML,
            )
            # auto-delete broadcast report after 1 hour
            schedule_delete_message(client, msg.chat.id, msg.id, delay_seconds=3600)
        except Exception:
            logger.exception("Failed to send broadcast report")