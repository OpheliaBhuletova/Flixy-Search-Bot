import os
import re
import json
import base64
import time
import random
import asyncio
import logging

from pyrogram import Client, filters, enums
from pyrogram.errors import ChatAdminRequired, FloodWait
from pyrogram.errors.exceptions.bad_request_400 import PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.utils.messages import Texts
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import get_size, is_subscribed
from bot.utils.helpers import get_settings, save_group_settings, get_file_id

from database.ia_filterdb import Media, get_file_details, unpack_new_file_id
from database.users_chats_db import db
from database.connections_mdb import active_connection

logger = logging.getLogger(__name__)

BATCH_FILES: dict = {}


# ─── START / GENID ────────────────────────────────────────────────────

@Client.on_message(filters.command("genid") & filters.private)
async def gen_file_id(client: Client, message: Message):
    msg = await message.reply_photo("images/start_1.png")
    await message.reply_text(
        f"FILE_ID:\n<code>{msg.photo.file_id}</code>",
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_message(filters.command("setstartup") & filters.private)
async def set_startup_image(client: Client, message: Message):
    """Set startup image from replied or attached image (admin only).
    
    Usage:
    - Reply to an image with /setstartup
    - Send /setstartup with an image attached
    """
    # Check if user is an admin
    if message.from_user.id not in settings.ADMINS:
        await message.reply("❌ This command is restricted to administrators only.")
        return
    
    # Get the image to process
    image_message = None
    
    if message.reply_to_message:
        image_message = message.reply_to_message
    elif (message.photo or message.document):
        image_message = message
    
    if not image_message:
        await message.reply("❌ Please reply to an image or send an image with this command.")
        return
    
    # Extract file_id
    file_info = get_file_id(image_message)
    
    if not file_info:
        await message.reply("❌ Could not extract file_id from the image.")
        return
    
    try:
        # Store in database
        await db.add_startup_image(file_info.file_id)
        
        # Log to console
        logger.info(f"Admin {message.from_user.id} set new startup image: {file_info.file_id}")
        
        # Send confirmation
        success_msg = (
            f"✅ <b>Startup image updated!</b>\n\n"
            f"<b>File ID:</b> <code>{file_info.file_id}</code>\n"
            f"<b>Media Type:</b> {file_info.message_type}\n\n"
            f"<i>The image will be used as a random option in the /start response.</i>"
        )
        await message.reply(success_msg, parse_mode=enums.ParseMode.HTML)
        
        # Notify to LOG_CHANNEL
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                user = message.from_user
                user_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
                username_str = f" (@{user.username})" if user.username else ""
                
                log_msg = (
                    f"<b>⚙️ Startup Image Updated</b>\n\n"
                    f"<b>Admin:</b> {user_link}{username_str}\n"
                    f"<b>Admin ID:</b> <code>{user.id}</code>\n"
                    f"<b>File ID:</b> <code>{file_info.file_id}</code>\n"
                    f"<b>Media Type:</b> {file_info.message_type}"
                )
                await client.send_message(log_channel, log_msg, parse_mode=enums.ParseMode.HTML)
            except Exception:
                logger.exception("Failed to notify LOG_CHANNEL about startup image update")
    
    except Exception as e:
        logger.exception("Error setting startup image")
        await message.reply(f"❌ Error: {str(e)}")


@Client.on_message(filters.command("ad") & filters.user(settings.ADMINS) & filters.private)
async def ad_toggle_handler(client: Client, message: Message):
    """Turn periodic ad sending on or off (admin only).

    Usage:
      /ad on  - enable ads
      /ad off - disable ads
    """
    if len(message.command) != 2:
        return await message.reply("Usage: /ad <on|off>")

    action = message.command[1].lower()
    if action not in ("on", "off"):
        return await message.reply("Usage: /ad <on|off>")

    enable = action == "on"

    try:
        await db.set_ad_enabled(enable)
        # update runtime cache so change takes effect immediately
        RuntimeCache.ad_enabled = enable

        await message.reply(f"✅ Ads {'enabled' if enable else 'disabled'}.")

        # notify log channel
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                await client.send_message(
                    log_channel,
                    f"Ads have been {'enabled' if enable else 'disabled'} by admin <a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception:
                logger.exception("Failed to notify LOG_CHANNEL about ad toggle")

    except Exception as e:
        logger.exception("Failed to set ad flag")
        await message.reply(f"❌ Error updating ad setting: {e}")


@Client.on_message(filters.command("start") & filters.incoming)
async def start_handler(client: Client, message: Message):
    # ── GROUP START ──
    if message.chat.type in {enums.ChatType.GROUP, enums.ChatType.SUPERGROUP}:
        buttons = [
            [InlineKeyboardButton("🤖 Updates", url="https://t.me/+w7aX0q-ex1U1NDc1")],
            [InlineKeyboardButton("❓Help", url=f"https://t.me/{RuntimeCache.bot_username}?start=help")]
        ]
        # create a mention string compatible with markdown (we always send markdown here)
        if message.from_user:
            user_mention = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"
        else:
            user_mention = message.chat.title

        await message.reply(
            Texts.START_TXT.format(
                user_mention,
                RuntimeCache.bot_username,
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.MARKDOWN,
        )

        await asyncio.sleep(2)

        if not await db.get_chat(message.chat.id):
            members = await client.get_chat_members_count(message.chat.id)
            
            # Log to database
            await db.add_chat(message.chat.id, message.chat.title)
            
            # Log to LOG_CHANNEL
            log_channel = getattr(settings, "LOG_CHANNEL", 0)
            if log_channel:
                try:
                    user_link = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>" if message.from_user else "Anonymous"
                    log_msg = (
                        f"🆕 <b>New Group Connected</b>\n\n"
                        f"<b>Group:</b> {message.chat.title} (<code>{message.chat.id}</code>)\n"
                        f"<b>Members:</b> <code>{members}</code>\n"
                        f"<b>Added By:</b> {user_link}"
                    )
                    await client.send_message(log_channel, log_msg, parse_mode=enums.ParseMode.HTML)
                except Exception:
                    logger.exception("Failed to send new group notification to LOG_CHANNEL")
        return

    # ── PRIVATE START ──
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        
        # Notify LOG_CHANNEL of new user registration
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                user_link = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>"
                username_str = f" (@{message.from_user.username})" if message.from_user.username else ""
                notification = (
                    f"<b>👤 New User Registered</b>\n\n"
                    f"User ID: <code>{message.from_user.id}</code>\n"
                    f"Name: {user_link}{username_str}"
                )
                await client.send_message(log_channel, notification, parse_mode=enums.ParseMode.HTML)
            except Exception:
                logger.exception("Failed to send new user notification to LOG_CHANNEL")

    if len(message.command) != 2:
        buttons = [
            [
                InlineKeyboardButton("🔍 Search", switch_inline_query_current_chat=""),
                InlineKeyboardButton("🤖 Updates", url="https://t.me/+w7aX0q-ex1U1NDc1")
            ],
            [
                InlineKeyboardButton("❓Help", callback_data="help"),
                InlineKeyboardButton("ℹ️ About", callback_data="about")
            ]
        ]
        
        # Get startup images from database and settings
        startup_images = []
        try:
            db_images = await db.get_startup_images()
            if db_images:
                startup_images = db_images
                logger.info(f"Using {len(db_images)} startup images from database")
            else:
                startup_images = list(settings.PICS)
                logger.info("No database images found, using default PICS")
        except Exception:
            logger.exception("Failed to get startup images from database, using defaults")
            startup_images = list(settings.PICS)
        
        # Use a random image from available options
        pic_to_use = random.choice(startup_images) if startup_images else settings.PICS[0]
        logger.info(f"Selected startup image: {pic_to_use[:50]}...")
        
        await message.reply_photo(
            pic_to_use,
            caption=Texts.START_TXT.format(
                message.from_user.mention,
                RuntimeCache.bot_username,
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML
        )
        return

    # AUTH_CHANNEL removed — no forced subscription required