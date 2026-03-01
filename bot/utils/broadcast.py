import asyncio
import logging
from pyrogram import Client, enums
from pyrogram.errors import (
    InputUserDeactivated,
    UserIsBlocked,
    PeerIdInvalid,
    FloodWait,
)
from pyrogram.types import Message
from bot.utils.cache import RuntimeCache
from bot.config import settings
from database.users_chats_db import db

logger = logging.getLogger(__name__)


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
    """Notify all users about a new movie title.

    This function iterates through the user list and sends a simple HTML
    message containing the *title*.  It also logs a short report to the
    configured log channel (if any).  Duplicate titles are prevented by
    checking the database before this function is called.
    """
    users = await db.get_all_users()
    # message text mirrors the style of the regular ad but is movie-specific
    msg_text = (
        f"🎬 <b>New movie added:</b> <i>{title}</i>\n\n"
        f"Use inline search (<code>@{RuntimeCache.bot_username} {title}</code>) "
        "or message me for details."
    )

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
            # gentle pacing to avoid floods
            await asyncio.sleep(1)

    # send a short report to the log channel if configured
    log_channel = getattr(settings, "LOG_CHANNEL", 0)
    if log_channel:
        try:
            report = (
                f"<b> Movie Broadcast Report</b>\n\n"
                f"Title: <code>{title}</code>\n"
                f"Total: {total}\n"
                f"Delivered: {success}\n"
                f"Blocked: {blocked}\n"
                f"Deleted: {deleted}\n"
                f"Failed: {failed}"
            )
            await client.send_message(log_channel, report, parse_mode=enums.ParseMode.HTML)
        except Exception:
            logger.exception("Failed to send movie broadcast report")
