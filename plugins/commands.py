import random
import asyncio
import logging

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.utils.messages import Texts
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import get_file_id

from database.users_chats_db import db

logger = logging.getLogger(__name__)

BATCH_FILES: dict = {}


# ─── START / GENID ────────────────────────────────────────────────────

@Client.on_message(filters.command("genid") & filters.private)
async def gen_file_id(client: Client, message: Message):
    """Get file_id from a replied message (photo, sticker, video, etc).
    
    Usage: Reply to a message with media and send /genid
    """
    if not message.reply_to_message:
        await message.reply(
            "❌ Please reply to a message with media (photo, sticker, video, etc) "
            "and then send /genid"
        )
        return
    
    media_message = message.reply_to_message
    file_id = None
    media_type = None
    
    # Extract file_id from different media types
    if media_message.photo:
        file_id = media_message.photo.file_id
        media_type = "Photo"
    elif media_message.sticker:
        file_id = media_message.sticker.file_id
        media_type = "Sticker"
    elif media_message.video:
        file_id = media_message.video.file_id
        media_type = "Video"
    elif media_message.document:
        file_id = media_message.document.file_id
        media_type = "Document"
    elif media_message.audio:
        file_id = media_message.audio.file_id
        media_type = "Audio"
    else:
        await message.reply("❌ The replied message doesn't contain any media.")
        return
    
    if file_id:
        await message.reply_text(
            f"<b>{media_type} FILE_ID:</b>\n<code>{file_id}</code>",
            parse_mode=enums.ParseMode.HTML
        )


@Client.on_message(filters.command("setstartup") & filters.private)
async def set_startup_image(client: Client, message: Message):
    """Set startup image from replied or attached photo (admin only).

    Usage:
    - Reply to a photo with /setstartup
    - Send /setstartup with a photo attached
    """
    if message.from_user.id not in settings.ADMINS:
        await message.reply("❌ This command is restricted to administrators only.")
        return

    image_message = None

    if message.reply_to_message:
        image_message = message.reply_to_message
    elif message.photo:
        image_message = message

    if not image_message:
        await message.reply(
            "❌ Please reply to a photo or send a photo with this command."
        )
        return

    file_info = get_file_id(image_message)

    if not file_info:
        await message.reply("❌ Could not extract file_id from the photo.")
        return

    if file_info.message_type != "photo":
        await message.reply(
            "❌ Only Telegram photos can be used as startup images.\n"
            "Please send the image as a photo, not as a document."
        )
        return

    try:
        await db.add_startup_image(file_info.file_id)

        logger.info(
            f"Admin {message.from_user.id} set new startup image: {file_info.file_id}"
        )

        success_msg = (
            f"✅ <b>Startup image updated!</b>\n\n"
            f"<b>File ID:</b> <code>{file_info.file_id}</code>\n"
            f"<b>Media Type:</b> {file_info.message_type}\n\n"
            f"<i>The image will be used as a random option in the /start response.</i>"
        )
        await message.reply(success_msg, parse_mode=enums.ParseMode.HTML)

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
                await client.send_message(
                    log_channel,
                    log_msg,
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                logger.exception("Failed to notify LOG_CHANNEL about startup image update")

    except Exception as e:
        logger.exception("Error setting startup image")
        await message.reply(f"❌ Error: {str(e)}")


@Client.on_message(filters.command("deleteallimages") & filters.private)
async def delete_all_images_command(client: Client, message: Message):
    """Delete all saved startup images (admin only).

    Usage: /deleteallimages
    """
    if message.from_user.id not in settings.ADMINS:
        await message.reply("❌ This command is restricted to administrators only.")
        return

    try:
        images = await db.get_startup_images()

        if not images:
            await message.reply("ℹ️ No startup images found to delete.")
            return

        image_count = len(images)
        await db.delete_all_startup_images()

        logger.info(
            f"Admin {message.from_user.id} deleted all {image_count} startup images"
        )

        success_msg = (
            f"✅ <b>All startup images deleted!</b>\n\n"
            f"<b>Images Deleted:</b> {image_count}\n\n"
            f"<i>The bot will now use the default startup images from the configuration.</i>"
        )
        await message.reply(success_msg, parse_mode=enums.ParseMode.HTML)

        # Log to LOG_CHANNEL
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                user = message.from_user
                user_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
                username_str = f" (@{user.username})" if user.username else ""
                log_msg = (
                    f"🖼️ <b>Startup Images Deleted</b>\n\n"
                    f"<b>Admin:</b> {user_link}{username_str}\n"
                    f"<b>Images Deleted:</b> {image_count}"
                )
                await client.send_message(
                    log_channel, log_msg, parse_mode=enums.ParseMode.HTML
                )
            except Exception as e:
                logger.exception(f"Failed to log image deletion to LOG_CHANNEL: {e}")

    except Exception as e:
        logger.exception(e)
        await message.reply(f"❌ Error deleting images: {e}")


async def send_text_start(message: Message, buttons):
    await message.reply_text(
        Texts.START_TXT.format(
            message.from_user.mention,
            RuntimeCache.bot_username,
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True,
    )


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
        RuntimeCache.ad_enabled = enable

        await message.reply(f"✅ Ads {'enabled' if enable else 'disabled'}.")

        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                await client.send_message(
                    log_channel,
                    f"Ads have been {'enabled' if enable else 'disabled'} by admin "
                    f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception:
                logger.exception("Failed to notify LOG_CHANNEL about ad toggle")

    except Exception as e:
        logger.exception("Failed to set ad flag")
        await message.reply(f"❌ Error updating ad setting: {e}")


@Client.on_message(filters.command("publishupdates") & filters.private)
async def publish_updates_handler(client: Client, message: Message):
    """Publish an image to the updates channel (admin only).

    Usage:
    - Reply to a message with an image: /publishupdates yes (with buttons)
    - Reply to a message with an image: /publishupdates no (without buttons)
    """
    if message.from_user.id not in settings.ADMINS:
        await message.reply("❌ This command is restricted to administrators only.")
        return

    if not message.reply_to_message:
        await message.reply("❌ Please reply to a message with an image.")
        return

    replied_message = message.reply_to_message

    # Check if the replied message has a photo
    if not replied_message.photo:
        await message.reply("❌ The replied message must contain a photo.")
        return

    # Check for parameter (yes/no)
    include_buttons = True
    if len(message.command) >= 2:
        param = message.command[1].lower()
        if param == "no":
            include_buttons = False
        elif param != "yes":
            await message.reply("Usage: /publishupdates <yes|no>")
            return

    try:
        # Copy the message with the image to the updates channel
        update_channel = -1003307506115
        update_sticker = "CAACAgUAAxkBAAOXaeUiJNVeBbgSpicTUbvvVllB8JYAAoweAALZY2BVBctCzpA2xKseBA"
        
        # Warm up the peer cache by sending a message first (like the LOG_CHANNEL pattern)
        try:
            chatz = await client.get_chat(-1003307506115)
            print(chatz.title)
            chat = await client.get_chat(update_channel)
            logger.info(f"Peer warmed: {chat.title}")
        except Exception as e:
            logger.warning(f"Failed to warm peer cache: {e}")
        
        # Send image first with or without buttons
        if include_buttons:
            buttons = [
                [
                    InlineKeyboardButton("ᴍᴏᴠɪᴇꜱ", url="https://t.me/+5FUtXWwDtTxhNTM1"),
                    InlineKeyboardButton("ᴛᴠ ꜱᴇʀɪᴇꜱ", url="https://t.me/+8Ue11G48SfEzNjc9")
                ],
                [
                    InlineKeyboardButton("ꜰʟɪxʏ ꜱᴇᴀʀᴄʜ ʙᴏᴛ", url="https://t.me/CSrchBot")
                ]
            ]
            
            try:
                caption_text = replied_message.caption or ""
                formatted_caption = f"<b><i>{caption_text}</i></b>" if caption_text else ""
                
                await client.send_photo(
                    chat_id=update_channel,
                    photo=replied_message.photo.file_id,
                    caption=formatted_caption,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            except Exception as e:
                logger.warning(f"Failed to send photo with buttons: {e}, falling back to copy_message")
                await client.copy_message(
                    chat_id=update_channel,
                    from_chat_id=replied_message.chat.id,
                    message_id=replied_message.id
                )
        else:
            await client.copy_message(
                chat_id=update_channel,
                from_chat_id=replied_message.chat.id,
                message_id=replied_message.id
            )
        
        # Then send the sticker
        try:
            await client.send_sticker(
                chat_id=update_channel,
                sticker=update_sticker
            )
        except Exception as e:
            logger.warning(f"Failed to send sticker: {e}")

        logger.info(
            f"Admin {message.from_user.id} published an update to channel {update_channel} "
            f"{'with buttons' if include_buttons else 'without buttons'}"
        )

        success_msg = (
            f"✅ <b>Update Published!</b>\n\n"
            f"<b>Channel:</b> <code>{update_channel}</code>\n"
            f"<i>The image {'with buttons' if include_buttons else 'without buttons'} and sticker have been sent.</i>"
        )
        await message.reply(success_msg, parse_mode=enums.ParseMode.HTML)

        # Log to LOG_CHANNEL
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                user = message.from_user
                user_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
                username_str = f" (@{user.username})" if user.username else ""

                log_msg = (
                    f"📢 <b>Update Published</b>\n\n"
                    f"<b>Admin:</b> {user_link}{username_str}\n"
                    f"<b>Admin ID:</b> <code>{user.id}</code>\n"
                    f"<b>Channel:</b> <code>{update_channel}</code>\n"
                    f"<b>With Buttons:</b> {'Yes' if include_buttons else 'No'}"
                )
                await client.send_message(
                    log_channel,
                    log_msg,
                    parse_mode=enums.ParseMode.HTML
                )
            except Exception:
                logger.exception("Failed to notify LOG_CHANNEL about update publication")

    except Exception as e:
        logger.exception(f"Error publishing update: {e}")
        await message.reply(f"❌ Error publishing update: {str(e)}")


@Client.on_message(filters.command("start") & filters.incoming)
async def start_handler(client: Client, message: Message):
    # ── GROUP START ──
    if message.chat.type in {enums.ChatType.GROUP, enums.ChatType.SUPERGROUP}:
        buttons = [
            [InlineKeyboardButton("🤖 Updates", url="https://t.me/+w7aX0q-ex1U1NDc1")],
            [InlineKeyboardButton("❓Help", url=f"https://t.me/{RuntimeCache.bot_username}?start=help")]
        ]

        if message.from_user:
            user_mention = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"
        else:
            user_mention = message.chat.title

        group_start_text = (
            f"👋 Hello {user_mention}!\n\n"
            f"🎬 I can help users search movies instantly.\n\n"
            f"🔎 Try inline search:\n"
            f"@{RuntimeCache.bot_username} movie name"
        )

        await message.reply(
            group_start_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.MARKDOWN,
        )

        await asyncio.sleep(2)

        try:
            if not await db.get_chat(message.chat.id):
                members = await client.get_chat_members_count(message.chat.id)

                await db.add_chat(message.chat.id, message.chat.title)

                log_channel = getattr(settings, "LOG_CHANNEL", 0)
                if log_channel:
                    try:
                        user_link = (
                            f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.first_name}</a>"
                            if message.from_user else "Anonymous"
                        )
                        log_msg = (
                            f"🆕 <b>New Group Connected</b>\n\n"
                            f"<b>Group:</b> {message.chat.title} (<code>{message.chat.id}</code>)\n"
                            f"<b>Members:</b> <code>{members}</code>\n"
                            f"<b>Added By:</b> {user_link}"
                        )
                        await client.send_message(
                            log_channel,
                            log_msg,
                            parse_mode=enums.ParseMode.HTML
                        )
                    except Exception:
                        logger.exception("Failed to send new group notification to LOG_CHANNEL")
        except Exception:
            logger.exception("Failed during group registration in /start")

        return

    # ── PRIVATE START ──
    try:
        if not await db.is_user_exist(message.from_user.id):
            await db.add_user(message.from_user.id, message.from_user.first_name)

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
                    await client.send_message(
                        log_channel,
                        notification,
                        parse_mode=enums.ParseMode.HTML
                    )
                except Exception:
                    logger.exception("Failed to send new user notification to LOG_CHANNEL")
    except Exception:
        logger.exception("User registration check failed during /start")

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

        startup_images = []
        try:
            db_images = await db.get_startup_images()
            if db_images:
                startup_images = db_images
                logger.info(f"Using {len(db_images)} startup images from database")
            else:
                logger.info("No startup images found in database, sending text-only start")
        except Exception:
            logger.exception("Failed to get startup images from database")
            startup_images = []

        if not startup_images:
            return await send_text_start(message, buttons)

        pic_to_use = random.choice(startup_images)
        logger.info(f"Selected startup image: {pic_to_use[:50]}...")

        try:
            await message.reply_photo(
                pic_to_use,
                caption=Texts.START_TXT.format(
                    message.from_user.mention,
                    RuntimeCache.bot_username,
                ),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            logger.exception("Failed to send startup image, sending text-only start")
            await send_text_start(message, buttons)

        return

    # AUTH_CHANNEL removed — no forced subscription required

    data = message.command[1]
    ...