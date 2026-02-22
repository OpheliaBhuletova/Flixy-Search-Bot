import asyncio
import logging
import logging.config
import os
from datetime import datetime
from typing import Union, Optional, AsyncGenerator

from pyrogram import Client, __version__, idle, enums
from pyrogram.raw.all import layer
from pyrogram import types
from pyrogram.errors import FloodWait

from aiohttp import web

from bot.config import settings, LOG_STR
from database.users_chats_db import get_db_instance
from database.ia_filterdb import Media
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
        db = get_db_instance()
        # Ensure DB indexes for users/chats are created on the running loop
        try:
            await db.ensure_indexes()
        except Exception:
            logger.exception("Failed to ensure users/chats indexes")
        banned_users, banned_chats = await db.get_banned()
        RuntimeCache.banned_users = banned_users
        RuntimeCache.banned_chats = banned_chats

        # start the web server early so health checks stay happy even if
        # bot authorization is delayed by a FloodWait
        web_app = await web_server()
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()

        # start Pyrogram client and handle authorization flood waits
        while True:
            try:
                await super().start()
                break
            except FloodWait as fw:  # Telegram rate limit
                wait = getattr(fw, 'x', None) or getattr(fw, 'value', None) or getattr(fw, 'seconds', None)
                if wait is None:
                    wait = fw.args[0] if fw.args else None
                logger.warning(
                    "FloodWait on bot authorization (%s seconds), sleeping before retry",
                    wait,
                )
                if wait:
                    await asyncio.sleep(wait)
                # loop and try again

        # Ensure DB indexes
        try:
            await Media.ensure_indexes()
        except Exception as e:  # pymongo.errors.OperationFailure if index already exists
            msg = str(e)
            # handle both "only one text index" (code 67) and
            # "equivalent index exists with different name/options" (code 85)
            if ("only one text index" in msg
                    or getattr(e, 'code', None) in (67, 85)):
                logger.warning("text index conflict detected; attempting to repair indexes: %s", e)
                # remove any existing text indexes so the new compound index can be created
                try:
                    coll = Media.collection
                    info = await coll.index_information()
                    for name, spec in info.items():
                        # spec['key'] is a list of tuples (field, direction)
                        if any(direction == 'text' for _, direction in spec.get('key', [])):
                            logger.info("dropping existing text index '%s'", name)
                            await coll.drop_index(name)
                    # retry creating indexes once
                    await Media.ensure_indexes()
                except Exception as e2:
                    logger.exception("failed to rebuild text indexes: %s", e2)
            else:
                raise

        # Bot identity
        me = await self.get_me()
        RuntimeCache.bot_username = me.username
        RuntimeCache.bot_name = me.first_name
        RuntimeCache.current = me.id
        RuntimeCache.startup_time = datetime.now()

        self.username = f"@{me.username}"

        logger.info(
            "%s started with Pyrogram v%s (Layer %s) as %s",
            me.first_name,
            __version__,
            layer,
            self.username,
        )
        logger.info(LOG_STR)

        # Attempt to send a startup message to the configured logs channel
        log_channel = getattr(settings, "LOG_CHANNEL", 0)

        if log_channel:
            try:
                # env vars often come as strings -> force int when numeric
                if isinstance(log_channel, str) and log_channel.lstrip("-").isdigit():
                    log_channel = int(log_channel)

                # Force resolve (gives clearer errors if bot isn't in chat)
                await self.get_chat(log_channel)

                await self.send_message(
                    log_channel,
                    f"<b>✅ Bot started</b>: {self.username}\n\n<pre>{LOG_STR}</pre>",
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception:
                logger.exception(f"Failed to send startup message to LOG_CHANNEL={log_channel!r}")

        # Note: Startup message to LOG_CHANNEL may fail for private channels
        # due to Pyrogram peer cache limitations with bots on private channels.
        # Once the channel receives any message from the bot, subsequent
        # messages will work normally.

        # Block forever so Koyeb does not scale down
        await asyncio.Event().wait()

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