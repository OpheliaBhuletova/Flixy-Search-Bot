import logging
import motor.motor_asyncio

from bot.config import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)



class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.grp = self.db.groups

        # Do not create indexes or schedule async work at import time.
        # Index creation will be performed explicitly from the running
        # event loop by calling `ensure_indexes()`.

    def _ensure_indexes(self):
        try:
            # Legacy synchronous helper kept for reference. Prefer
            # using the async `ensure_indexes` method below.
            self.col.create_index("id", unique=True)
            self.col.create_index("ban_status.is_banned")

            self.grp.create_index("id", unique=True)
            self.grp.create_index("chat_status.is_disabled")
        except Exception:
            logger.exception("Failed creating MongoDB indexes")

    async def ensure_indexes(self):
        """Asynchronously create necessary indexes. Call this from a running
        asyncio event loop (for example during bot startup) so Motor's
        coroutines are attached to the correct loop."""
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
            "template": settings.IMDB_TEMPLATE,
        }

    async def update_settings(self, id, settings):
        await self.grp.update_one(
            {"id": int(id)},
            {"$set": {"settings": settings}},
        )

    async def get_settings(self, id):
        chat = await self.grp.find_one({"id": int(id)})
        return chat.get("settings", self.default_settings()) if chat else self.default_settings()

    # ─── Stats ───────────────────────────────────────────────────────────
    async def get_db_size(self):
        stats = await self.db.command("dbstats")
        return stats.get("dataSize", 0)

_db_instance = None

def get_db_instance():
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(
            settings.DATABASE_URL,
            settings.DATABASE_NAME
        )
    return _db_instance

# Keep a module-level instance for backwards compatibility. It will be
# created on import but won't run async index creation until explicitly
# invoked from the event loop via `ensure_indexes()`.
db = get_db_instance()