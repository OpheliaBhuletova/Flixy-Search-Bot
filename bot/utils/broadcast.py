import asyncio
import logging
from pyrogram.errors import (
    InputUserDeactivated,
    UserIsBlocked,
    PeerIdInvalid,
    FloodWait,
)
from pyrogram.types import Message
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