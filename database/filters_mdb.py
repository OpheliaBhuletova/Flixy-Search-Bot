import logging
from typing import List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import enums

from bot.config import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

# ─── Mongo Client ───────────────────────────────────────────────────────
mongo_client = AsyncIOMotorClient(settings.DATABASE_URL)
database = mongo_client[settings.DATABASE_NAME]


# ─── Filters ────────────────────────────────────────────────────────────

async def add_filter(
    grp_id: int,
    text: str,
    reply_text: str,
    btn: str,
    file: Optional[str],
    alert: Optional[str],
) -> None:
    collection = database[str(grp_id)]

    data = {
        "text": str(text),
        "reply": str(reply_text),
        "btn": str(btn),
        "file": str(file),
        "alert": str(alert),
    }

    try:
        # Ensure index for faster lookup
        await collection.create_index("text")

        await collection.update_one(
            {"text": text},
            {"$set": data},
            upsert=True,
        )
    except Exception as e:
        logger.exception("Failed to add filter", exc_info=e)


async def find_filter(group_id: int, name: str) -> Tuple:
    collection = database[str(group_id)]

    try:
        doc = await collection.find_one({"text": name})
        if not doc:
            return None, None, None, None

        return (
            doc.get("reply"),
            doc.get("btn"),
            doc.get("alert"),
            doc.get("file"),
        )

    except Exception as e:
        logger.exception("Failed to find filter", exc_info=e)
        return None, None, None, None


async def get_filters(group_id: int) -> List[str]:
    collection = database[str(group_id)]
    texts: List[str] = []

    try:
        async for doc in collection.find({}, {"text": 1}):
            texts.append(doc["text"])
    except Exception as e:
        logger.exception("Failed to get filters", exc_info=e)

    return texts


async def delete_filter(message, text: str, group_id: int) -> None:
    collection = database[str(group_id)]

    count = await collection.count_documents({"text": text})
    if count == 1:
        await collection.delete_one({"text": text})
        await message.reply_text(
            f"`{text}` deleted. I won't respond to it anymore.",
            quote=True,
            parse_mode=enums.ParseMode.MARKDOWN,
        )
    else:
        await message.reply_text("Couldn't find that filter!", quote=True)


async def del_all(message, group_id: int, title: str) -> None:
    collection_name = str(group_id)

    if collection_name not in await database.list_collection_names():
        await message.edit_text(f"Nothing to remove in {title}!")
        return

    try:
        await database.drop_collection(collection_name)
        await message.edit_text(f"All filters from **{title}** have been removed.")
    except Exception as e:
        logger.exception("Failed to delete all filters", exc_info=e)
        await message.edit_text("Couldn't remove all filters from this group!")


async def count_filters(group_id: int) -> Optional[int]:
    collection = database[str(group_id)]
    count = await collection.count_documents({})
    return count if count > 0 else False


async def filter_stats() -> Tuple[int, int]:
    collections = await database.list_collection_names()

    if "CONNECTION" in collections:
        collections.remove("CONNECTION")

    total_count = 0
    for name in collections:
        collection = database[name]
        total_count += await collection.count_documents({})

    return len(collections), total_count