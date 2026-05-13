import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message

from bot.config import settings
from database.mongo import get_inline_collection, get_pm_collection, get_db

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("recentfiles") & filters.user(settings.ADMINS))
async def recent_files_handler(client: Client, message: Message):
    """
    Display recently added files to MOVIES_CHANNELS and SERIES_CHANNELS.
    
    Usage: /recentfiles [movies|series|both] [limit]
    Examples:
        /recentfiles - Shows last 5 files from both
        /recentfiles movies 10 - Shows last 10 movies
        /recentfiles series 5 - Shows last 5 series
    """
    try:
        args = message.text.split()
        filter_type = args[1].lower() if len(args) > 1 else "both"
        limit = int(args[2]) if len(args) > 2 else 5
        
        if filter_type not in ["movies", "series", "both"]:
            return await message.reply("❌ Invalid filter. Use: movies, series, or both")
        
        if limit > 50:
            limit = 50
        
        msg = await message.reply("📊 Fetching recent files...")
        
        text = f"📊 <b>Recent Files ({limit} per category)</b>\n\n"
        
        # Fetch from MOVIES DB (Inline)
        if filter_type in ["movies", "both"]:
            try:
                movies_collection = get_inline_collection()
                
                movies = await movies_collection.find().sort("created_at", -1).limit(limit).to_list(length=limit)
                
                if movies:
                    text += "📌 <b>MOVIES DB (moviesDB)</b>\n"
                    for idx, file in enumerate(movies, 1):
                        file_name = file.get('file_name', 'Unknown')[:40]
                        file_size = file.get('file_size', 0)
                        size_mb = file_size / (1024 * 1024) if file_size else 0
                        text += f"{idx}. <code>{file_name}</code> ({size_mb:.2f}MB)\n"
                    text += "\n"
                else:
                    text += "📌 <b>MOVIES DB (moviesDB)</b> - No files\n\n"
            except Exception as e:
                logger.exception(f"Error fetching movies: {e}")
                text += f"⚠️ Error fetching movies: {e}\n\n"
        
        # Fetch from SERIES DB (PM)
        if filter_type in ["series", "both"]:
            try:
                series_collection = get_pm_collection()
                
                series = await series_collection.find().sort("created_at", -1).limit(limit).to_list(length=limit)
                
                if series:
                    text += "💬 <b>SERIES DB (seriesDB)</b>\n"
                    for idx, file in enumerate(series, 1):
                        file_name = file.get('file_name', 'Unknown')[:40]
                        file_size = file.get('file_size', 0)
                        size_mb = file_size / (1024 * 1024) if file_size else 0
                        text += f"{idx}. <code>{file_name}</code> ({size_mb:.2f}MB)\n"
                    text += "\n"
                else:
                    text += "💬 <b>SERIES DB (seriesDB)</b> - No files\n\n"
            except Exception as e:
                logger.exception(f"Error fetching series: {e}")
                text += f"⚠️ Error fetching series: {e}\n\n"
        
        text += "\n💡 <b>Usage:</b>\n"
        text += "<code>/recentfiles [movies|series|both] [limit]</code>\n\n"
        text += "<b>Examples:</b>\n"
        text += "<code>/recentfiles movies 10</code> - Last 10 movies\n"
        text += "<code>/recentfiles series 5</code> - Last 5 series"
        
        await msg.edit(text, parse_mode=enums.ParseMode.HTML)
        
    except Exception as e:
        logger.exception(f"Error in recent_files_handler: {e}")
        await message.reply(f"❌ Error: {e}")


@Client.on_message(filters.command("dbstats") & filters.user(settings.ADMINS))
async def database_stats_handler(client: Client, message: Message):
    """
    Display database statistics for MOVIES_CHANNELS and SERIES_CHANNELS.
    
    Shows:
    - Total files in each database
    - Total storage size
    - Configuration info
    """
    try:
        msg = await message.reply("📊 Fetching database stats...")
        
        stats = "📊 <b>Database Statistics</b>\n\n"
        
        # MOVIES DB Stats
        try:
            movies_collection = get_inline_collection()
            
            movies_count = await movies_collection.count_documents({})
            movies_size = await movies_collection.aggregate([
                {"$group": {"_id": None, "total_size": {"$sum": "$file_size"}}}
            ]).to_list(length=1)
            
            movies_total_size = movies_size[0]['total_size'] if movies_size else 0
            movies_size_gb = movies_total_size / (1024 * 1024 * 1024)
            
            stats += f"📌 <b>MOVIES DB (moviesDB)</b>\n"
            stats += f"• Files: <code>{movies_count}</code>\n"
            stats += f"• Total Size: <code>{movies_size_gb:.2f} GB</code>\n"
            stats += f"• Channel(s): <code>{settings.MOVIES_CHANNELS}</code>\n\n"
        except Exception as e:
            logger.exception(f"Error fetching movies stats: {e}")
            stats += f"⚠️ MOVIES DB Error: {e}\n\n"
        
        # SERIES DB Stats
        try:
            series_collection = get_pm_collection()
            
            series_count = await series_collection.count_documents({})
            series_size = await series_collection.aggregate([
                {"$group": {"_id": None, "total_size": {"$sum": "$file_size"}}}
            ]).to_list(length=1)
            
            series_total_size = series_size[0]['total_size'] if series_size else 0
            series_size_gb = series_total_size / (1024 * 1024 * 1024)
            
            stats += f"💬 <b>SERIES DB (seriesDB)</b>\n"
            stats += f"• Files: <code>{series_count}</code>\n"
            stats += f"• Total Size: <code>{series_size_gb:.2f} GB</code>\n"
            stats += f"• Channel(s): <code>{settings.SERIES_CHANNELS}</code>\n\n"
        except Exception as e:
            logger.exception(f"Error fetching series stats: {e}")
            stats += f"⚠️ SERIES DB Error: {e}\n\n"
        
        # Configuration Info
        stats += f"⚙️ <b>Configuration</b>\n"
        stats += f"• Multi-DB Enabled: <code>{settings.ENABLE_MULTI_DB}</code>\n"
        stats += f"• Movies Collection: <code>Cluster0</code>\n"
        stats += f"• Series Collection: <code>Cluster0</code>"
        
        await msg.edit(stats, parse_mode=enums.ParseMode.HTML)
        
    except Exception as e:
        logger.exception(f"Error in database_stats_handler: {e}")
        await message.reply(f"❌ Error: {e}")
