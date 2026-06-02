from pyrogram import Client, filters, enums
import logging

from pyrogram.types import Message

from bot.config import settings
from database.ia_filterdb import save_file, save_file_inline, save_file_pm, announce_title
from database.users_chats_db import db
from bot.services.metadata_service import search_tmdb_titles
from bot.utils.helpers import extract_series_name_from_file, schedule_delete_message
from bot.utils.broadcast import new_movie_broadcast

logger = logging.getLogger(__name__)


MEDIA_FILTER = filters.document | filters.video | filters.audio
WATCHLIST_NOTIFICATION_CHANNEL = -1003707238605


@Client.on_message(
    (
        filters.chat(settings.MOVIES_CHANNELS) |
        filters.chat(settings.SERIES_CHANNELS) |
        filters.chat(settings.CHANNELS) |
        filters.chat(WATCHLIST_NOTIFICATION_CHANNEL)
    ) & MEDIA_FILTER
)
async def channel_media_handler(client: Client, message: Message):
    """
    Handles media messages from configured channels
    and saves them into the appropriate database.
    Also notifies users who have added the series to their watchlist.
    """
    logger.info(f"📥 Media handler triggered for channel: {message.chat.id} ({message.chat.title})")
    
    media = None
    file_type = None

    for kind in ("document", "video", "audio"):
        media = getattr(message, kind, None)
        if media:
            file_type = kind
            break

    if not media:
        logger.debug(f"No media found in message {message.id}")
        return

    logger.info(f"📎 Found media type: {file_type}, File name: {media.file_name}")
    
    media.file_type = file_type
    media.caption = message.caption

    # Determine which database to save to based on channel type
    if message.chat.id in settings.MOVIES_CHANNELS:
        logger.info(f"💾 Saving to MOVIES DB (inline/moviesDB): {media.file_name}")
        saved, reason, title = await save_file_inline(media)
    elif message.chat.id in settings.SERIES_CHANNELS:
        logger.info(f"💾 Saving to SERIES DB (PM/seriesDB): {media.file_name}")
        saved, reason, title = await save_file_pm(media)
    else:
        logger.info(f"💾 Saving to DEFAULT DB: {media.file_name}")
        saved, reason, title = await save_file(media)
    
    logger.info(f"💾 Save result - Saved: {saved}, Reason: {reason}, Title: {title}")
    
    if saved:
        logger.info(f"✅ File saved successfully: {title}")
        
        # Log to Telegram LOG_CHANNEL for tracking
        if settings.LOG_CHANNEL and message.chat.id != WATCHLIST_NOTIFICATION_CHANNEL:
            try:
                db_type = "📌 MOVIES DB (moviesDB)" if message.chat.id in settings.MOVIES_CHANNELS else "💬 SERIES DB (seriesDB)" if message.chat.id in settings.SERIES_CHANNELS else "📦 DEFAULT DB"
                log_msg = f"✅ <b>File Added</b>\n\n<b>DB:</b> {db_type}\n<b>Title:</b> <code>{title}</code>\n<b>File:</b> <code>{media.file_name}</code>\n<b>Size:</b> <code>{media.file_size / (1024*1024):.2f} MB</code>\n<b>Channel:</b> {message.chat.title}"
                sent_log = await client.send_message(settings.LOG_CHANNEL, log_msg, parse_mode=enums.ParseMode.HTML)
                schedule_delete_message(client, sent_log.chat.id, sent_log.id, delay_seconds=3600)
            except Exception as e:
                logger.warning(f"Failed to log to LOG_CHANNEL: {e}")
        
        logger.info(f"🔔 Checking if title '{title}' is new...")
        is_new = await announce_title(title)
        logger.info(f"🔔 announce_title returned: {is_new}")
        
        # If from watchlist channel, ONLY notify watchlist users (not broadcast to all)
        if message.chat.id == WATCHLIST_NOTIFICATION_CHANNEL:
            logger.info(f"📺 Message from watchlist notification channel, processing watchlist notifications only")
            if is_new:
                try:
                    await _notify_watchlist_users(client, message, media)
                    logger.info(f"✅ Watchlist notifications sent for: {title}")
                except Exception as e:
                    logger.exception(f"Error notifying watchlist users: {e}")
        else:
            # For other channels, broadcast to all users
            if is_new:
                logger.info(f"🎬 New title '{title}' detected, but global broadcast is temporarily disabled.")
                # try:
                #     await new_movie_broadcast(client, title, message)
                #     logger.info(f"✅ Broadcast completed for: {title}")
                # except Exception as e:
                #     logger.exception(f"❌ Error during broadcast for '{title}': {e}")
                pass
            else:
                logger.info(f"ℹ️  Title '{title}' was already announced, skipping broadcast")
    else:
        logger.warning(f"⚠️  File not saved - Reason: {reason} (0=duplicate, 2=error)")


async def _notify_watchlist_users(client: Client, message: Message, media):
    """Extract series name from the file and notify users who have it in their watchlist."""
    # Extract series name from file name ONLY (ignore caption for now)
    logger.debug(f"   Input filename: {media.file_name}")
    logger.debug(f"   Input caption: {message.caption}")
    
    series_name = extract_series_name_from_file(str(media.file_name), None)
    
    logger.debug(f"   Extracted name attempt 1: {series_name}")
    
    if not series_name or len(series_name.strip()) < 2:
        logger.warning(f"⚠️  Could not extract proper series name from media - extracted: '{series_name}'")
        return
    
    logger.info(f"📺 Extracted series name: {series_name}")
    
    # Extract season and episode numbers from filename
    import re
    season_episode = ""
    se_match = re.search(r"[Ss](\d{1,2})[Ee](\d{1,2})", str(media.file_name))
    if se_match:
        season_num = se_match.group(1).lstrip("0") or "0"
        episode_num = se_match.group(2).lstrip("0") or "0"
        season_episode = f"Season {season_num} Episode {episode_num}"
        logger.info(f"📺 Extracted season/episode: {season_episode}")
    
    # Search for the series on TMDB to get ID and media type
    logger.debug(f"🔍 Searching TMDB for: {series_name}")
    search_results = await search_tmdb_titles(series_name, preferred_type="tv", limit=1)
    logger.debug(f"🔍 TMDB search returned {len(search_results) if search_results else 0} results: {search_results}")
    
    if not search_results:
        if not settings.TMDB_API_KEY:
            logger.warning(f"⚠️  TMDB_API_KEY not configured - cannot search for series: {series_name}")
            logger.warning(f"   Please add TMDB_API_KEY to your .env file")
        else:
            logger.warning(f"⚠️  No TMDB results found for series: '{series_name}'")
            logger.info(f"   Try searching on https://www.themoviedb.org/ to verify the series exists")
        logger.debug(f"   Filename was: {media.file_name}")
        return
    
    series_info = search_results[0]
    tmdb_id = series_info.get("id")
    media_type = series_info.get("media_type", "tv")
    series_title = series_info.get("title", series_name)
    
    if not tmdb_id:
        logger.warning(f"⚠️  Could not extract TMDB ID for: {series_name}")
        return
    
    logger.info(f"🎬 Found TMDB ID: {tmdb_id} | Title: {series_title} | Type: {media_type}")
    
    # Find all users who have this series in their watchlist
    user_ids = await db.get_users_with_series_in_watchlist(tmdb_id, media_type)
    
    if not user_ids:
        logger.info(f"ℹ️  No users have {series_name} in their watchlist")
        return
    
    logger.info(f"📢 Notifying {len(user_ids)} users about new episode of '{series_title}'")
    logger.info(f"👥 User IDs: {user_ids}")
    
    # Send notifications to each user (separate messages)
    notification_text = f"🎉 Hey! Your watchlisted series just got a new episode:\n\n<b>{series_title}</b>"
    if season_episode:
        notification_text += f"\n{season_episode}"
    
    success_count = 0
    failed_users = []
    
    for user_id in user_ids:
        try:
            # First message: Text notification
            await client.send_message(
                user_id,
                notification_text,
                parse_mode=enums.ParseMode.HTML
            )
            logger.info(f"✅ Notification text sent to user {user_id}")
            
            # Second message: The file with original caption
            if message.video:
                await client.send_video(
                    user_id,
                    video=message.video.file_id,
                    caption=message.caption.html if message.caption else None,
                    parse_mode=enums.ParseMode.HTML if message.caption else None
                )
            elif message.document:
                await client.send_document(
                    user_id,
                    document=message.document.file_id,
                    caption=message.caption.html if message.caption else None,
                    parse_mode=enums.ParseMode.HTML if message.caption else None
                )
            elif message.audio:
                await client.send_audio(
                    user_id,
                    audio=message.audio.file_id,
                    caption=message.caption.html if message.caption else None,
                    parse_mode=enums.ParseMode.HTML if message.caption else None
                )
            logger.info(f"✅ File sent to user {user_id}")
            success_count += 1
        except Exception as e:
            logger.warning(f"❌ Failed to notify user {user_id}: {e}")
            failed_users.append(user_id)
            continue
    
    logger.info(f"📊 Watchlist notification summary for '{series_title}':")
    logger.info(f"   ✅ Delivered: {success_count}/{len(user_ids)}")
    if failed_users:
        logger.info(f"   ❌ Failed: {failed_users}")