from typing import List, Optional
import logging

from motor.motor_asyncio import AsyncIOMotorClient

from info import DATABASE_URI, DATABASE_NAME

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

# ─── Mongo Client ───────────────────────────────────────────────────────
mongo_client = AsyncIOMotorClient(DATABASE_URI)
database = mongo_client[DATABASE_NAME]
collection = database["CONNECTION"]


# ─── Connection Management ──────────────────────────────────────────────

async def add_connection(group_id: str, user_id: str) -> bool:
    """
    Add a group connection for a user and set it as active.
    """
    try:
        query = await collection.find_one(
            {"_id": user_id},
            {"_id": 0, "active_group": 0}
        )

        if query:
            group_ids = [x["group_id"] for x in query.get("group_details", [])]
            if group_id in group_ids:
                return False

        group_details = {"group_id": group_id}

        if not query:
            data = {
                "_id": user_id,
                "group_details": [group_details],
                "active_group": group_id,
            }
            await collection.insert_one(data)
        else:
            await collection.update_one(
                {"_id": user_id},
                {
                    "$push": {"group_details": group_details},
                    "$set": {"active_group": group_id},
                },
            )

        return True

    except Exception as e:
        logger.exception("Failed to add connection", exc_info=e)
        return False


async def active_connection(user_id: str) -> Optional[int]:
    """
    Return currently active group ID for a user.
    """
    query = await collection.find_one(
        {"_id": user_id},
        {"_id": 0, "group_details": 0},
    )

    if not query:
        return None

    group_id = query.get("active_group")
    return int(group_id) if group_id is not None else None


async def all_connections(user_id: str) -> Optional[List[str]]:
    """
    Return all connected group IDs for a user.
    """
    query = await collection.find_one(
        {"_id": user_id},
        {"_id": 0, "active_group": 0},
    )

    if not query:
        return None

    return [x["group_id"] for x in query.get("group_details", [])]


async def if_active(user_id: str, group_id: str) -> bool:
    """
    Check if a group is the currently active connection.
    """
    query = await collection.find_one(
        {"_id": user_id},
        {"_id": 0, "group_details": 0},
    )

    return bool(query and query.get("active_group") == group_id)


async def make_active(user_id: str, group_id: str) -> bool:
    """
    Set a group as active connection.
    """
    result = await collection.update_one(
        {"_id": user_id},
        {"$set": {"active_group": group_id}},
    )
    return result.modified_count > 0


async def make_inactive(user_id: str) -> bool:
    """
    Remove active group connection.
    """
    result = await collection.update_one(
        {"_id": user_id},
        {"$set": {"active_group": None}},
    )
    return result.modified_count > 0


async def delete_connection(user_id: str, group_id: str) -> bool:
    """
    Delete a group connection and reassign active group if needed.
    """
    try:
        result = await collection.update_one(
            {"_id": user_id},
            {"$pull": {"group_details": {"group_id": group_id}}},
        )

        if result.modified_count == 0:
            return False

        query = await collection.find_one({"_id": user_id})

        group_details = query.get("group_details", [])
        active_group = query.get("active_group")

        if group_details:
            if active_group == group_id:
                new_active = group_details[-1]["group_id"]
                await collection.update_one(
                    {"_id": user_id},
                    {"$set": {"active_group": new_active}},
                )
        else:
            await collection.update_one(
                {"_id": user_id},
                {"$set": {"active_group": None}},
            )

        return True

    except Exception as e:
        logger.exception("Failed to delete connection", exc_info=e)
        return False