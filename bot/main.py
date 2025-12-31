import asyncio
import logging
import logging.config
import os
from typing import Union, Optional, AsyncGenerator

from pyrogram import Client, __version__, idle
from pyrogram.raw.all import layer
from pyrogram import types

from aiohttp import web

from bot.config import settings, LOG_STR
from bot.database.client import db
from bot.database.ia_filterdb import Media
from bot.utils.cache import RuntimeCache
from plugins import web_server


# ─── Logging setup ────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.config.fileConfig(
    "bot/logging.conf",
    disable_existing_loggers=False
)

logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)


PORT = int(os.getenv("PORT", 8080))


class Bot(Client):
    def __init__(self):
        super().__init__(
            name=settings.SESSION,
            api_id=settings.API_ID,
            api_hash=settings.API_HASH,
            bot_token=settings.BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5,
        )

    async def start(self):
        # Load banned users/chats
        banned_users, banned_chats = await db.get_banned()
        RuntimeCache.banned_users = banned_users
        RuntimeCache.banned_chats = banned_chats

        await super().start()

        # Ensure DB indexes
        await Media.ensure_indexes()

        # Bot identity
        me = await self.get_me()
        RuntimeCache.bot_username = me.username
        RuntimeCache.bot_name = me.first_name
        RuntimeCache.current = me.id

        self.username = f"@{me.username}"

        # Start web server
        app = web.AppRunner(await web_server())
        await app.setup()
        await web.TCPSite(app, "0.0.0.0", PORT).start()

        logger.info(
            "%s started with Pyrogram v%s (Layer %s) as %s",
            me.first_name,
            __version__,
            layer,
            self.username,
        )
        logger.info(LOG_STR)

    async def stop(self, *args):
        await super().stop()
        logger.info("Bot stopped. Bye.")

    async def iter_messages(
        self,
        chat_id: Union[int, str],
        limit: int,
        offset: int = 0,
    ) -> Optional[AsyncGenerator[types.Message, None]]:
        """
        Legacy helper to iterate messages sequentially.
        NOTE: Pyrogram already provides iter_messages().
        Kept for backward compatibility.
        """
        current = offset
        while True:
            diff = min(200, limit - current)
            if diff <= 0:
                return
            messages = await self.get_messages(
                chat_id,
                list(range(current, current + diff + 1))
            )
            for message in messages:
                yield message
                current += 1


async def main():
    app = Bot()
    await app.start()
    await idle()
    await app.stop()


if __name__ == "__main__":
    asyncio.run(main())