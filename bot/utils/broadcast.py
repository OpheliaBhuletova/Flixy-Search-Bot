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
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.utils.cache import RuntimeCache
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

async def new_movie_broadcast(client: Client, title: str):
    """Notify all users about a newly indexed movie title."""
    users = await db.get_all_users()
    movie_title, movie_year = _split_title_year(title)
    display_name = f"{movie_title} ({movie_year})" if movie_year else movie_title
    msg_text = (
        "🎬 <b>New Movie Added</b>\n\n"
        f"<b>Title:</b> {movie_title}\n"
        f"<b>Year:</b> {movie_year or 'N/A'}\n\n"
        "🔎 <b>Search instantly:</b>\n"
        f"Use inline search — <code>@{RuntimeCache.bot_username} {display_name}</code>\n\n"
        "📩 <b>Or send me the movie name in PM</b> to get the file."
    )

    buttons = [[
        InlineKeyboardButton(
            "🔎 Search Instantly",
            switch_inline_query_current_chat=title,
        )
    ]]

    total = await db.total_users_count()
    done = success = blocked = deleted = failed = 0

    async for user in users:
        uid = int(user["id"])
        try:
            await client.send_message(
                uid,
                msg_text,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(buttons),
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
            logger.exception("Failed to send movie broadcast to %s", uid)
            failed += 1
        finally:
            done += 1
            await asyncio.sleep(1)

    log_channel = getattr(settings, "LOG_CHANNEL", 0)
    if log_channel:
        try:
            report = (
                "🎬 <b>Movie Broadcast Report</b>\n\n"
                f"<b>Title:</b> <code>{title}</code>\n"
                f"<b>Total:</b> {total}\n"
                f"<b>Delivered:</b> {success}\n"
                f"<b>Blocked:</b> {blocked}\n"
                f"<b>Deleted:</b> {deleted}\n"
                f"<b>Failed:</b> {failed}"
            )
            await client.send_message(
                log_channel,
                report,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            logger.exception("Failed to send movie broadcast report")