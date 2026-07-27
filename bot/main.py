import asyncio
import logging
import logging.config
import os
import time
from datetime import datetime
from typing import AsyncGenerator, Optional, Union

import aiohttp
from aiohttp import web
from pyrogram import Client, __version__, idle, enums
from pyrogram.errors import FloodWait, PeerIdInvalid, MessageNotModified

from bot.config import LOG_STR, settings
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import get_size, schedule_delete_message
from database.ott_db import ensure_ott_indexes # New import
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.ia_filterdb import Media, get_inline_collection, get_pm_collection
from database.users_chats_db import get_db_instance
from plugins import web_server

logging.basicConfig(level=logging.INFO)
logging.info(f"--- RUNNING PYROTQFORK VERSION: {__version__} ---")

# ─── Logging setup ────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.config.fileConfig("bot/logging.conf", disable_existing_loggers=False)

logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

PORT = int(os.getenv("PORT", 8080))


# ─── Startup log helper (Pyrogram -> Bot API fallback) ────────────────
async def botapi_send_message(token: str, chat_id: int, text: str, reply_markup: dict = None) -> None:
    import json
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=payload) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise RuntimeError(data)


async def send_startup_log(app: Client, chat_id: int, text: str, reply_markup=None):
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
            reply_markup=reply_markup,
        )
        return msg
    except Exception as e:
        if "Peer id invalid" not in str(e):
            raise

    # fallback: Bot API can't give us a message object
    reply_markup_dict = None
    if reply_markup:
        reply_markup_dict = reply_markup.to_dict()

    await botapi_send_message(app.bot_token, chat_id, text, reply_markup=reply_markup_dict)
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
        self.status_update_task: Optional[asyncio.Task] = None

    async def _update_status_message(self):
        """Periodically update the live status message."""
        db = get_db_instance()
        while True:
            await asyncio.sleep(300)  # Update every 5 minutes

            if not (RuntimeCache.status_message_id and RuntimeCache.status_message_chat_id):
                continue

            try:
                # 1. Uptime
                uptime_seconds = (datetime.now() - RuntimeCache.startup_time).total_seconds()
                days, remainder = divmod(int(uptime_seconds), 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

                # 2. Database Stats
                movies_collection = get_inline_collection()
                movies_count = await movies_collection.count_documents({})
                movies_size_agg = await movies_collection.aggregate([{"$group": {"_id": None, "total_size": {"$sum": "$file_size"}}}]).to_list(length=1)
                movies_total_size = movies_size_agg[0]['total_size'] if movies_size_agg else 0

                series_collection = get_pm_collection()
                series_count = await series_collection.count_documents({})
                series_size_agg = await series_collection.aggregate([{"$group": {"_id": None, "total_size": {"$sum": "$file_size"}}}]).to_list(length=1)
                series_total_size = series_size_agg[0]['total_size'] if series_size_agg else 0

                total_files = movies_count + series_count
                total_size = movies_total_size + series_total_size

                # 3. User Stats
                total_users = await db.total_users_count()
                total_chats = await db.total_chat_count()

                # Channel counts
                total_channels = len(settings.MOVIES_CHANNELS) + len(settings.SERIES_CHANNELS)

                # 4. Ping
                ping_start = time.perf_counter()
                await self.get_me()
                ping_ms = (time.perf_counter() - ping_start) * 1000

                status_message_text = (
                    f"📊 <b>Flixy Live Status</b>\n\n"
                    f"<b>Bot Status:</b> <code>Online</code>\n"
                    f"<b>Uptime:</b> <code>{uptime_str}</code>\n"
                    f"<b>Ping:</b> <code>{ping_ms:.2f} ms</code>\n\n"
                    f"🗄 <b>Database Summary</b>\n"
                    f"• <b>Total Files:</b> <code>{total_files:,}</code>\n"
                    f"• <b>Total Users:</b> <code>{total_users:,}</code>\n"
                    f"• <b>Total Channels:</b> <code>{total_channels}</code>\n"
                    f"• <b>Total Group Chats:</b> <code>{total_chats:,}</code>"
                )

                await self.edit_message_text(
                    chat_id=RuntimeCache.status_message_chat_id,
                    message_id=RuntimeCache.status_message_id,
                    text=status_message_text,
                    parse_mode=enums.ParseMode.HTML,
                    disable_web_page_preview=True
                )
                logger.info("Updated live status message.")
            except MessageNotModified:
                pass  # No changes, do nothing
            except asyncio.CancelledError:
                logger.info("Status update task cancelled.")
                break
            except Exception:
                logger.exception("Failed to update live status message.")

    async def start(self):
        RuntimeCache.startup_time = datetime.now()
        
        # Pre-flight check: Ensure mandatory multi-cluster database URLs are provided
        # to prevent defaulting to 'localhost' and causing connection timeouts.
        if not settings.DATABASE_URL_INLINE or not settings.DATABASE_URL_PM:
            logger.critical("FATAL: DATABASE_URL_INLINE and DATABASE_URL_PM are required to start the bot.")
            return

        # Load banned users/chats + ensure indexes
        db = get_db_instance()
        try:
            await db.ensure_indexes()
        except Exception:
            logger.exception("Failed to ensure user/chat indexes")
        
        try:
            await ensure_ott_indexes() # Ensure indexes for OTT messages
        except Exception:
            logger.exception("Failed to ensure OTT messages indexes")

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
                wait = getattr(fw, "value", 0) or (fw.args[0] if fw.args else 60)
                logger.warning("FloodWait on bot authorization (%s seconds), sleeping before retry", wait)
                if wait:
                    await asyncio.sleep(wait)

        # Ensure DB indexes for media
        try:
            await Media.ensure_indexes()
        except Exception as e:
            msg = str(e)
            if "only one text index" in msg or getattr(e, "code", None) in (67, 85):
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
        RuntimeCache.bot_id = me.id
        RuntimeCache.bot_username = me.username
        RuntimeCache.bot_name = me.first_name
        RuntimeCache.current = me.id

        # Load persisted ad flag
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
                ping_start = time.perf_counter()
                await self.get_me()
                ping_ms = (time.perf_counter() - ping_start) * 1000
                
                startup_msg = (
                    f"<b>🚀 Flixy Search Bot Online</b>\n\n"
                    f"<blockquote>\n"
                    f"Metadata: {('TMDb ✓' if settings.METADATA_ENABLED else 'Disabled ✗')}\n"
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
                # Auto-delete startup log after 60 seconds
                if msg:
                    schedule_delete_message(self, msg.chat.id, msg.id, delay_seconds=60)
            except Exception:
                logger.exception("Failed to send startup log to LOG_CHANNEL")

        # Send live status message to the intro channel
        try:
            intro_channel_id = -1003865668861
            
            # Check for and delete previous live status message if it exists
            if RuntimeCache.status_message_id and RuntimeCache.status_message_chat_id:
                try:
                    await self.delete_messages(
                        chat_id=RuntimeCache.status_message_chat_id,
                        message_ids=RuntimeCache.status_message_id,
                    )
                    logger.info("Deleted previous live status message on startup.")
                except Exception:
                    logger.exception("Failed to delete previous live status message on startup.")


            # 1. Uptime
            uptime_seconds = (datetime.now() - RuntimeCache.startup_time).total_seconds()
            days, remainder = divmod(int(uptime_seconds), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

            # 2. Database Stats
            movies_collection = get_inline_collection()
            movies_count = await movies_collection.count_documents({})
            movies_size_agg = await movies_collection.aggregate([{"$group": {"_id": None, "total_size": {"$sum": "$file_size"}}}]).to_list(length=1)
            movies_total_size = movies_size_agg[0]['total_size'] if movies_size_agg else 0

            series_collection = get_pm_collection()
            series_count = await series_collection.count_documents({})
            series_size_agg = await series_collection.aggregate([{"$group": {"_id": None, "total_size": {"$sum": "$file_size"}}}]).to_list(length=1)
            series_total_size = series_size_agg[0]['total_size'] if series_size_agg else 0

            total_files = movies_count + series_count
            total_size = movies_total_size + series_total_size

            # 3. User Stats
            total_users = await db.total_users_count()
            total_chats = await db.total_chat_count()

            # Channel counts
            total_channels = len(settings.MOVIES_CHANNELS) + len(settings.SERIES_CHANNELS)

            # 4. Ping
            ping_start = time.perf_counter()
            await self.get_me()
            ping_ms = (time.perf_counter() - ping_start) * 1000

            live_status_text = (
                f"📊 <b>Flixy Live Status</b>\n\n"
                f"<b>Bot Status:</b> <code>Online</code>\n"
                f"<b>Uptime:</b> <code>{uptime_str}</code>\n"
                f"<b>Ping:</b> <code>{ping_ms:.2f} ms</code>\n\n"
                f"🗄 <b>Database Summary</b>\n"
                f"• <b>Total Files:</b> <code>{total_files:,}</code>\n"
                f"• <b>Total Users:</b> <code>{total_users:,}</code>\n"
                f"• <b>Total Channels:</b> <code>{total_channels}</code>\n"
                f"• <b>Total Group Chats:</b> <code>{total_chats:,}</code>"
            )

            status_message = await send_startup_log(self, intro_channel_id, live_status_text)
            if status_message:
                RuntimeCache.status_message_id = status_message.id
                RuntimeCache.status_message_chat_id = status_message.chat.id
                try:
                    await status_message.pin()
                    logger.info(f"Pinned live status message in {intro_channel_id}")
                except Exception:
                    logger.exception(f"Failed to pin live status message in {intro_channel_id}")

                logger.info(f"Sent live status message to {intro_channel_id} (msg_id: {status_message.id})")
                self.status_update_task = asyncio.create_task(self._update_status_message())
            else:
                logger.warning(
                    f"Could not get message ID for status message sent to {intro_channel_id}. "
                    "This may happen if the bot is not a member of the channel. "
                    "Live status updates will not work."
                )

            # Send the "What's New" message separately
            whats_new_section = (
                "<b>What's New in This Update:</b>\n\n"
                "• <b>Separate Startup Messages:</b> The 'Flixy Live Status' and 'What's New' sections are now sent as separate messages for better clarity and easier updates.\n"
                "• <b>Auto-Delete for File Deletion Logs:</b> Log messages for deleted files in the `LOG_CHANNEL` will now automatically be deleted after 1 hour, mirroring the behavior of 'File Added' messages.\n"
                "• <b>Private Message Search:</b> The bot now responds to search queries in private messages for all users, not just administrators.\n"
                "• <b>UI Refresh:</b> The OTT Release Calendar has been updated with a cleaner, more consistent color scheme for easier navigation."
            )
            await send_startup_log(self, intro_channel_id, whats_new_section)
            logger.info(f"Sent 'What's New' message to {intro_channel_id}")

        except Exception:
            logger.exception(f"Failed to send startup messages to channel {intro_channel_id}")

        # Start periodic ad sender if channels are configured
        if getattr(settings, "AD_CHANNEL", None):
            async def _ad_sender(app: Client):
                interval, delete_after = 6 * 3600, 3 * 3600
                while True:
                    # Refresh persisted flag at start of loop
                    try:
                        ad_enabled = await db.get_ad_enabled()
                        RuntimeCache.ad_enabled = bool(ad_enabled)
                    except Exception:
                        ad_enabled = getattr(RuntimeCache, "ad_enabled", False)

                    if ad_enabled:
                        for ch in settings.AD_CHANNEL:
                            try:
                                msg_text = (
                                    "<b>🚀 Tired of Searching Everywhere for Movies?</b>\n\n"
                                    "🍿 Let <b>F L I X Y</b> do it for you.\n\n"
                                    "🔎 Smart Inline Search\n"
                                    "⚡ Lightning Fast Results\n"
                                    "🎬 Movies & Series in Seconds\n\n"
                                    "No complicated steps. Just type and get what you want.\n\n"
                                )
                                buttons = InlineKeyboardMarkup(
                                    [[InlineKeyboardButton("Try Flixy", url=f"https://t.me/{RuntimeCache.bot_username}", style=enums.ButtonStyle.PRIMARY)]]
                                )
                                sent = await app.send_message(
                                    ch,
                                    msg_text,
                                    parse_mode=enums.ParseMode.HTML,
                                    disable_web_page_preview=True,
                                    reply_markup=buttons,
                                )
                                schedule_delete_message(app, sent.chat.id, sent.id, delay_seconds=delete_after)
                            except Exception as exc:
                                # Fallback to Bot API if peer is invalid
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
        if self.status_update_task:
            self.status_update_task.cancel()

        if RuntimeCache.status_message_id and RuntimeCache.status_message_chat_id:
            try:
                await self.delete_messages(
                    chat_id=RuntimeCache.status_message_chat_id,
                    message_ids=RuntimeCache.status_message_id,
                )
                logger.info("Deleted live status message on shutdown.")
            except Exception:
                logger.exception("Failed to delete live status message on shutdown.")

        await super().stop()
        logger.info("Bot stopped. Bye.")


async def main():
    app = Bot()
    await app.start()
    await idle()
    await app.stop()


if __name__ == "__main__":
    asyncio.run(main())