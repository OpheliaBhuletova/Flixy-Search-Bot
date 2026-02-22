import asyncio
import logging
import logging.config
import os
from datetime import datetime
from typing import AsyncGenerator, Optional, Union

import aiohttp
from aiohttp import web
from pyrogram import Client, __version__, idle, types, enums
from pyrogram.errors import FloodWait

from bot.config import LOG_STR, settings
from bot.utils.cache import RuntimeCache
from database.ia_filterdb import Media
from database.users_chats_db import get_db_instance
from plugins import web_server


# ─── Logging setup ────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.config.fileConfig("bot/logging.conf", disable_existing_loggers=False)

logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)

PORT = int(os.getenv("PORT", 8080))


# ─── Startup log helper (Pyrogram -> Bot API fallback) ────────────────
async def botapi_send_message(token: str, chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=payload) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise RuntimeError(data)


async def send_startup_log(app: Client, chat_id: int, text: str) -> None:
    # Try Pyrogram first; fall back to Bot API for "Peer id invalid" issue.
    try:
        await app.send_message(
            chat_id,
            text,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return
    except Exception as e:
        if "Peer id invalid" not in str(e):
            raise

    await botapi_send_message(app.bot_token, chat_id, text)


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
        # Load banned users/chats + ensure indexes
        db = get_db_instance()
        try:
            await db.ensure_indexes()
        except Exception:
            logger.exception("Failed to ensure users/chats indexes")

        RuntimeCache.banned_users, RuntimeCache.banned_chats = await db.get_banned()

        # Web server for health checks
        web_app = await web_server()
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()

        # Start Pyrogram with FloodWait handling
        while True:
            try:
                await super().start()
                break
            except FloodWait as fw:
                wait = getattr(fw, "value", None) or getattr(fw, "x", None) or getattr(fw, "seconds", None)
                wait = wait or (fw.args[0] if fw.args else None)
                logger.warning("FloodWait on bot authorization (%s seconds), sleeping before retry", wait)
                if wait:
                    await asyncio.sleep(wait)

        # Ensure DB indexes for media
        try:
            await Media.ensure_indexes()
        except Exception as e:
            msg = str(e)
            if ("only one text index" in msg) or (getattr(e, "code", None) in (67, 85)):
                logger.warning("text index conflict detected; attempting to repair indexes: %s", e)
                try:
                    coll = Media.collection
                    info = await coll.index_information()
                    for name, spec in info.items():
                        if any(direction == "text" for _, direction in spec.get("key", [])):
                            logger.info("dropping existing text index '%s'", name)
                            await coll.drop_index(name)
                    await Media.ensure_indexes()
                except Exception:
                    logger.exception("failed to rebuild text indexes")
            else:
                raise

        # Bot identity
        me = await self.get_me()
        RuntimeCache.bot_username = me.username
        RuntimeCache.bot_name = me.first_name
        RuntimeCache.current = me.id
        RuntimeCache.startup_time = datetime.now()

        self.username = f"@{me.username}"

        logger.info("%s started with Pyrogram v%s as %s", me.first_name, __version__, self.username)
        logger.info(LOG_STR)

        # Startup log
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                await send_startup_log(
                    self,
                    int(log_channel),
                    f"<b>✅ Bot started</b>: {self.username}\n\n<blockquote>{LOG_STR}</blockquote>",
                )
            except Exception:
                logger.exception("Failed to send startup message to LOG_CHANNEL")

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
            messages = await self.get_messages(chat_id, list(range(current, current + diff + 1)))
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


#def build_log_string(ping: int = 0, boot_time: float = 0.0) -> str:
#    return f"""
#<b>🚀 Flixy Search Bot Online</b>
#
#<pre>
#IMDB:        {"Enabled ✓" if settings.IMDB else "Disabled ✗"}
#SpellCheck:  {"Enabled ✓" if settings.SPELL_CHECK_REPLY else "Disabled ✗"}
#Max Results: {settings.MAX_LIST_ELM if settings.MAX_LIST_ELM else "Default"}
#</pre>
#
#⚡ Ping: <b>{ping} ms</b>
#⏱ Boot: <b>{round(boot_time, 2)}s</b>
#
#Ready.
#"""