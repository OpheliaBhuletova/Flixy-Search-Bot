import logging
import motor.motor_asyncio
from typing import List, Dict, Optional

from bot.config import settings

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.grp = self.db.groups

    async def ensure_indexes(self):
        """Asynchronously create necessary indexes for users and groups collections."""
        try:
            await self.col.create_index("id", unique=True)
            await self.col.create_index("ban_status.is_banned")

            await self.grp.create_index("id", unique=True)
            await self.grp.create_index("chat_status.is_disabled")
        except Exception:
            logger.exception("Failed creating MongoDB indexes (async)")

    # ─── User Helpers ────────────────────────────────────────────────────
    def new_user(self, id, name):
        return {
            "id": id,
            "name": name,
            "ban_status": {
                "is_banned": False,
                "ban_reason": "",
            },
            "watchlist": [],
        }

    async def add_user(self, id, name):
        if not await self.is_user_exist(id):
            await self.col.insert_one(self.new_user(id, name))

    async def is_user_exist(self, id):
        return bool(await self.col.find_one({"id": int(id)}, {"_id": 1}))

    async def total_users_count(self):
        return await self.col.count_documents({})

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({"id": int(user_id)})

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Retrieves a user document by user_id."""
        return await self.col.find_one({"id": int(user_id)})

    # ─── Watchlist ───────────────────────────────────────────────────────
    async def get_watchlist(self, user_id: int) -> List[Dict]:
        """Retrieves the watchlist for a user."""
        user = await self.col.find_one({"id": int(user_id)})
        if user:
            return user.get("watchlist", [])
        return []

    async def add_to_watchlist(self, user_id: int, tmdb_id: int, media_type: str) -> bool:
        """Adds a TV series to the user's watchlist. Returns True if added, False if already exists."""
        # Check if item already exists in watchlist
        user = await self.col.find_one(
            {"id": int(user_id), "watchlist": {"$elemMatch": {"tmdb_id": tmdb_id, "media_type": media_type}}}
        )

        if user:
            return False  # Already in watchlist

        # Add to watchlist
        await self.col.update_one(
            {"id": int(user_id)},
            {"$push": {"watchlist": {"tmdb_id": tmdb_id, "media_type": media_type}}},
            upsert=True
        )
        return True

    async def remove_from_watchlist(self, user_id: int, tmdb_id: int, media_type: str) -> bool:
        """Removes a TV series from the user's watchlist. Returns True if removed, False if not found."""
        result = await self.col.update_one(
            {"id": int(user_id)},
            {"$pull": {"watchlist": {"tmdb_id": tmdb_id, "media_type": media_type}}}
        )
        return result.modified_count > 0

    # ─── Ban System ──────────────────────────────────────────────────────
    async def ban_user(self, user_id, ban_reason="No Reason"):
        await self.col.update_one(
            {"id": int(user_id)},
            {"$set": {"ban_status": {"is_banned": True, "ban_reason": ban_reason}}},
        )

    async def remove_ban(self, id):
        await self.col.update_one(
            {"id": int(id)},
            {"$set": {"ban_status": {"is_banned": False, "ban_reason": ""}}},
        )

    async def get_ban_status(self, id):
        default = {"is_banned": False, "ban_reason": ""}
        user = await self.col.find_one({"id": int(id)})
        return user.get("ban_status", default) if user else default

    async def get_banned(self):
        users = self.col.find({"ban_status.is_banned": True})
        chats = self.grp.find({"chat_status.is_disabled": True})

        banned_users = [u["id"] async for u in users]
        banned_chats = [c["id"] async for c in chats]
        return banned_users, banned_chats

    # ─── Group Helpers ───────────────────────────────────────────────────
    def new_group(self, id, title):
        return {
            "id": id,
            "title": title,
            "chat_status": {
                "is_disabled": False,
                "reason": "",
            },
            "settings": self.default_settings(),
        }

    async def add_chat(self, chat, title):
        if not await self.grp.find_one({"id": int(chat)}):
            await self.grp.insert_one(self.new_group(chat, title))

    async def get_chat(self, chat):
        grp = await self.grp.find_one({"id": int(chat)})
        return False if not grp else grp.get("chat_status")

    async def disable_chat(self, chat, reason="No Reason"):
        await self.grp.update_one(
            {"id": int(chat)},
            {"$set": {"chat_status": {"is_disabled": True, "reason": reason}}},
        )

    async def re_enable_chat(self, id):
        await self.grp.update_one(
            {"id": int(id)},
            {"$set": {"chat_status": {"is_disabled": False, "reason": ""}}},
        )

    async def total_chat_count(self):
        return await self.grp.count_documents({})

    async def get_all_chats(self):
        return self.grp.find({})

    # ─── Settings ────────────────────────────────────────────────────────
    def default_settings(self):
        return {
            "button": settings.SINGLE_BUTTON,
            "botpm": settings.P_TTI_SHOW_OFF,
            "file_secure": settings.PROTECT_CONTENT,
            "imdb": settings.IMDB,
            "spell_check": settings.SPELL_CHECK_REPLY,
            "welcome": settings.MELCOW_NEW_USERS,
            "template": settings.METADATA_TEMPLATE,
        }

    async def update_settings(self, id, settings):
        await self.grp.update_one(
            {"id": int(id)},
            {"$set": {"settings": settings}},
        )

    async def get_settings(self, id):
        chat = await self.grp.find_one({"id": int(id)})
        return chat.get("settings", self.default_settings()) if chat else self.default_settings()

    # ─── Startup Images ────────────────────────────────────────────────────
    async def add_startup_image(self, file_id):
        await self.db.startup_images.update_one(
            {"_id": "images"},
            {"$addToSet": {"file_ids": file_id}},
            upsert=True
        )

    async def get_startup_images(self):
        doc = await self.db.startup_images.find_one({"_id": "images"})
        if doc:
            return doc.get("file_ids", [])
        return []

    async def remove_startup_image(self, file_id):
        await self.db.startup_images.update_one(
            {"_id": "images"},
            {"$pull": {"file_ids": file_id}}
        )

    async def delete_all_startup_images(self):
        """Delete all saved startup images."""
        await self.db.startup_images.delete_one({"_id": "images"})

    # ─── Bot-wide settings helpers ───────────────────────────────────
    async def set_ad_enabled(self, enabled: bool):
        """Persist the ad enabled flag for the bot.

        Stored in collection `bot_settings` with document id `ads_enabled`.
        """
        await self.db.bot_settings.update_one(
            {"_id": "ads_enabled"},
            {"$set": {"enabled": bool(enabled)}},
            upsert=True,
        )

    async def get_ad_enabled(self) -> bool:
        """Return True if ads are enabled in persistent storage, else False."""
        doc = await self.db.bot_settings.find_one({"_id": "ads_enabled"})
        return bool(doc and doc.get("enabled", False))

    # ─── Watchlist Notifications ──────────────────────────────────────
    async def get_users_with_series_in_watchlist(self, tmdb_id: int, media_type: str = "tv") -> List[int]:
        """Find all users who have a specific series in their watchlist."""
        users = await self.col.find(
            {"watchlist": {"$elemMatch": {"tmdb_id": tmdb_id, "media_type": media_type}}}
        ).to_list(None)
        return [user["id"] for user in users if "id" in user]

    # ─── Stats ───────────────────────────────────────────────────────────
    async def get_db_size(self):
        stats = await self.db.command("dbstats")
        return stats.get("dataSize", 0)

_db_instance = None

def get_db_instance():
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(
            settings.DATABASE_URL_PM,
            settings.DATABASE_NAME_PM
        )
    return _db_instance

db = get_db_instance()