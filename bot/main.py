import asyncio
import logging
import logging.config
import os
import time
from datetime import datetime
from typing import AsyncGenerator, Optional, Union

import aiohttp
from aiohttp import web
from pyrogram import Client, __version__, idle, types, enums
from pyrogram.errors import FloodWait, PeerIdInvalid

from bot.config import LOG_STR, settings
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import schedule_delete_message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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


async def send_startup_log(app: Client, chat_id: int, text: str):
    """Send a startup notification and return the sent Message if available.

    Falls back to Bot API on PeerIdInvalid, in which case ``None`` is returned
    since the Bot API response isn't wrapped in a Message object.
    """
    try:
        msg = await app.send_message(
            chat_id,
            text,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return msg
    except Exception as e:
        if "Peer id invalid" not in str(e):
            raise

    # fallback: Bot API can't give us a message object
    await botapi_send_message(app.bot_token, chat_id, text)
    return None


async def botapi_get_chat(token: str, chat_id: int) -> dict | None:
    """Fetch chat info via Bot API. Returns dict with 'title' and 'id' or None on failure."""
    url = f"https://api.telegram.org/bot{token}/getChat"
    payload = {"chat_id": chat_id}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as resp:
                data = await resp.json()
                if data.get("ok") and data.get("result"):
                    result = data["result"]
                    return {
                        "id": result.get("id"),
                        "title": result.get("title"),
                        "username": result.get("username"),
                    }
    except Exception:
        pass
    return None


async def get_chat_info(app: Client, chat_id: int) -> dict | None:
    """Try Pyrogram first; fall back to Bot API for 'Peer id invalid' issue."""
    try:
        chat = await app.get_chat(chat_id)
        return {
            "id": chat.id,
            "title": chat.title,
            "username": chat.username,
        }
    except Exception as e:
        if "Peer id invalid" not in str(e):
            raise
    
    return await botapi_get_chat(app.bot_token, chat_id)


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
        # Capture startup time at the very beginning
        RuntimeCache.startup_time = datetime.now()
        
        # Load banned users/chats + ensure indexes
        db = get_db_instance()
        try:
            await db.ensure_indexes()
        except Exception:
            logger.exception("Failed to ensure users/chats indexes")

        RuntimeCache.banned_users, RuntimeCache.banned_chats = await db.get_banned()
        # make sure sudo users are not accidentally treated as banned
        if settings.SUDO_USERS:
            RuntimeCache.banned_users = [
                u for u in RuntimeCache.banned_users if u not in settings.SUDO_USERS
            ]

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

        # load persisted ad flag into runtime cache (default: False)
        try:
            RuntimeCache.ad_enabled = await db.get_ad_enabled()
        except Exception:
            RuntimeCache.ad_enabled = False

        self.username = f"@{me.username}"

        logger.info("%s started with Pyrogram v%s as %s", me.first_name, __version__, self.username)
        logger.info(LOG_STR)

        # Startup log
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                boot_duration = (datetime.now() - RuntimeCache.startup_time).total_seconds()
                
                # Measure ping
                ping_start = time.perf_counter()
                await self.get_me()
                ping_ms = (time.perf_counter() - ping_start) * 1000
                
                startup_msg = (
                    f"<b>🚀 Flixy Search Bot Online</b>\n\n"
                    f"<blockquote>\n"
                    f"IMDB:        <b>{('Enabled ✓' if settings.IMDB else 'Disabled ✗')}</b>\n"
                    f"SpellCheck:  <b>{('Enabled ✓' if settings.SPELL_CHECK_REPLY else 'Disabled ✗')}</b>\n"
                    f"Max Results: <b>{(settings.MAX_LIST_ELM if settings.MAX_LIST_ELM else 'Default')}</b>\n"
                    f"</blockquote>\n\n"
                    f"⚡ Ping: <b>{ping_ms:.0f}</b> ms\n"
                    f"⏱ Boot: <b>{boot_duration:.2f}s</b>\n\n"
                    f"Ready."
                )
                msg = await send_startup_log(
                    self,
                    int(log_channel),
                    startup_msg,
                )
                # delete log message after 5 minutes if we got a message object
                if msg:
                    schedule_delete_message(self, msg.chat.id, msg.id, delay_seconds=300)
            except Exception:
                logger.exception("Failed to send startup log to LOG_CHANNEL")

        # Start periodic ad sender if channels are configured
        if getattr(settings, "AD_CHANNEL", None):
            async def _ad_sender(app: Client):
                # interval: 6 hours, delete_after: 3 hours
                interval = 6 * 3600
                delete_after = 3 * 3600
                while True:
                    # refresh persisted flag at start of loop
                    try:
                        ad_enabled = await db.get_ad_enabled()
                        RuntimeCache.ad_enabled = bool(ad_enabled)
                    except Exception:
                        ad_enabled = getattr(RuntimeCache, "ad_enabled", False)

                    if ad_enabled:
                        for ch in settings.AD_CHANNEL:
                            try:
                                # hardcoded ad message (HTML)
                                msg_text = (
                                    "<b>🚀 Tired of Searching Everywhere for Movies?</b>\n\n"
                                    "🍿 Let <b>F L I X Y</b> do it for you.\n\n"
                                    "🔎 Smart Inline Search\n"
                                    "⚡ Lightning Fast Results\n"
                                    "🎬 Movies & Series in Seconds\n\n"
                                    "No complicated steps. Just type and get what you want.\n\n"
                                    "<i>Start now 👉 @FSrchBot</i>"
                                )
                                buttons = InlineKeyboardMarkup(
                                    [[InlineKeyboardButton("Try Flixy", url=f"https://t.me/{RuntimeCache.bot_username}" )]]
                                )
                                sent = await app.send_message(
                                    ch,
                                    msg_text,
                                    parse_mode=enums.ParseMode.HTML,
                                    disable_web_page_preview=True,
                                    reply_markup=buttons,
                                )
                                # schedule deletion after delete_after seconds
                                schedule_delete_message(app, sent.chat.id, sent.id, delay_seconds=delete_after)
                            except Exception as exc:
                                # if peer is invalid (ValueError from utils or PeerIdInvalid),
                                # try sending via Bot API instead of logging an error.
                                is_peer_error = (
                                    (isinstance(exc, ValueError) and "Peer id invalid" in str(exc))
                                    or isinstance(exc, PeerIdInvalid)
                                )
                                if is_peer_error:
                                    try:
                                        await botapi_send_message(app.bot_token, ch, msg_text)
                                        logger.info("Sent ad to %s using Bot API fallback", ch)
                                    except Exception:
                                        logger.exception("Bot API also failed for ad to %s", ch)
                                else:
                                    logger.exception("Failed to send scheduled ad to %s", ch)

                    await asyncio.sleep(interval)

            try:
                asyncio.create_task(_ad_sender(self))
            except Exception:
                logger.exception("Failed to start ad sender task")

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