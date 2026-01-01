import asyncio
import logging
from pyrogram.errors import (
    InputUserDeactivated,
    UserIsBlocked,
    PeerIdInvalid,
    FloodWait,
)
from pyrogram.types import Message
from database.client import db

logger = logging.getLogger(__name__)


async def broadcast_messages(user_id: int, message: Message):
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"

    except FloodWait as e:
        await asyncio.sleep(e.value)
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