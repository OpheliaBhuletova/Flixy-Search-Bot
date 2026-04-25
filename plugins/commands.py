import random
import asyncio
import logging
import re
import html
import aiohttp

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.errors import PeerIdInvalid

from bot.config import settings
from bot.utils.messages import Texts
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import get_file_id

from database.users_chats_db import db

logger = logging.getLogger(__name__)

# ─── Bot API fallback helper ──────────────────────────────────────────
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


def extract_tg_post_id(text: str) -> int | None:
    if not text:
        return None

    patterns = [
        r"(?:https?://)?t\.me/(?:c/[^/]+|[^/]+)/(?P<id>\d+)",
        r"tg://resolve\?[^\s]*post=(?P<id>\d+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group("id"))
    return None


def extract_tg_post_id_from_message(message: Message) -> int | None:
    return extract_tg_post_id(message.text or "") or extract_tg_post_id(message.caption or "")


BATCH_FILES: dict = {}


# ─── Link parsing helpers ────────────────────────────────────────────────
def extract_channel_post_id(text: str) -> tuple[str, int] | None:
    """Extract channel username/ID and message ID from Telegram post link.
    
    Supports:
    - https://t.me/channel_username/12345
    - https://t.me/c/123456789/12345
    - tg://resolve?domain=channel_username&msgId=12345
    
    Returns: (channel_identifier, message_id) or None if not found
    """
    if not text:
        return None
    
    # Pattern 1 (check first - more specific): https://t.me/c/channel_id/message_id
    match = re.search(r'https://t\.me/c/(\d+)/(\d+)', text)
    if match:
        return (match.group(1), int(match.group(2)))
    
    # Pattern 2: https://t.me/username/message_id
    match = re.search(r'https://t\.me/([a-zA-Z0-9_]+)/(\d+)', text)
    if match:
        print(f"Extracted from /c/ link: channel_id={match.group(1)}, message_id={match.group(2)}")
        return (match.group(1), int(match.group(2)))
    
    # Pattern 3: tg://resolve?domain=username&msgId=12345
    match = re.search(r'tg://resolve\?domain=([a-zA-Z0-9_]+)&msgId=(\d+)', text)
    if match:
        return (match.group(1), int(match.group(2)))
    
    return None


def is_telegram_post_link(text: str) -> bool:
    """Check if text contains a Telegram channel post link."""
    return extract_channel_post_id(text) is not None


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
    """Publish to updates channel (admin only).

    Usage:
    - Reply to a photo: /publishupdates yes (with buttons) or /publishupdates no (without buttons)
    - Reply to a Telegram post link: /publishupdates New message text
    """
    if message.from_user.id not in settings.ADMINS:
        await message.reply("❌ This command is restricted to administrators only.")
        return

    if not message.reply_to_message:
        await message.reply("❌ Please reply to a message.")
        return

    replied_message = message.reply_to_message

    # Determine mode: photo or link
    is_photo_mode = bool(replied_message.photo)
    is_link_mode = bool(replied_message.text and is_telegram_post_link(replied_message.text))

    if not is_photo_mode and not is_link_mode:
        await message.reply(
            "❌ Please reply to either:\n"
            "1️⃣ A photo (then use: /publishupdates yes/no)\n"
            "2️⃣ A Telegram post link (then use: /publishupdates Your message text)"
        )
        return

    # Parse parameters based on mode
    include_buttons = True
    reply_text = None
    
    if is_photo_mode:
        # Photo mode: parse yes/no
        if len(message.command) >= 2:
            param = message.command[1].lower()
            if param == "no":
                include_buttons = False
            elif param != "yes":
                await message.reply("Usage (photo): /publishupdates yes|no")
                return
    else:
        # Link mode: extract message text inside double quotes
        if message.text:
            # Look for text inside double quotes
            quote_match = re.search(r'\"(.+?)\"', message.text)
            if quote_match:
                reply_text = quote_match.group(1)
                logger.info(f"Extracted reply text: {reply_text}")
            else:
                reply_text = ""
                logger.info(f"No quotes found in: {message.text}")
        else:
            reply_text = ""

    try:
        # Get updates channel from config
        update_channel = getattr(settings, "UPDATES_CHANNEL", 0)
        
        if not update_channel:
            await message.reply(
                "❌ Updates channel is not configured. "
                "Admin must set UPDATES_CHANNEL in environment variables."
            )
            return
        
        update_sticker = "CAACAgUAAxkBAAOXaeUiJNVeBbgSpicTUbvvVllB8JYAAoweAALZY2BVBctCzpA2xKseBA"
        fallback_used = False
        
        # ──── PHOTO MODE ────
        if is_photo_mode:
            # Prepare formatted caption (always bold and italics)
            caption_text = replied_message.caption or ""
            formatted_caption = f"<b><i>{caption_text}</i></b>" if caption_text else ""
            
            try:
                if include_buttons:
                    buttons = [
                        [
                            InlineKeyboardButton("👍", callback_data="emoji_thumbs_up"),
                            InlineKeyboardButton("👎", callback_data="emoji_thumbs_down"),
                            InlineKeyboardButton("❤️", callback_data="emoji_love")
                        ],
                        [
                            InlineKeyboardButton("Movies", url="https://t.me/+5FUtXWwDtTxhNTM1"),
                            InlineKeyboardButton("TV Series", url="https://t.me/+8Ue11G48SfEzNjc9")
                        ],
                        [
                            InlineKeyboardButton("Flixy Search Bot", url="https://t.me/CSrchBot")
                        ]
                    ]
                    
                    await client.send_photo(
                        chat_id=update_channel,
                        photo=replied_message.photo.file_id,
                        caption=formatted_caption,
                        parse_mode=enums.ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                else:
                    await client.send_photo(
                        chat_id=update_channel,
                        photo=replied_message.photo.file_id,
                        caption=formatted_caption,
                        parse_mode=enums.ParseMode.HTML
                    )
                
                # Then send the sticker
                await client.send_sticker(
                    chat_id=update_channel,
                    sticker=update_sticker
                )
            except Exception as exc:
                is_peer_error = (
                    (isinstance(exc, ValueError) and "Peer id invalid" in str(exc))
                    or isinstance(exc, PeerIdInvalid)
                )
                if is_peer_error:
                    try:
                        fallback_text = f"<b>📢 New Update</b>\n\n{formatted_caption}\n\n"
                        if include_buttons:
                            fallback_text += (
                                "🟢 <a href='https://t.me/+5FUtXWwDtTxhNTM1'>ᴍᴏᴠɪᴇꜱ</a> | "
                                "🔵 <a href='https://t.me/+8Ue11G48SfEzNjc9'>ᴛᴠ ꜱᴇʀɪᴇꜱ</a>\n"
                                "🟡 <a href='https://t.me/CSrchBot'>ꜰʟɪxʏ ꜱᴇᴀʀᴄʜ ʙᴏᴛ</a>"
                            )
                        await botapi_send_message(client.bot_token, update_channel, fallback_text)
                        logger.info("Sent update to %s using Bot API fallback", update_channel)
                        fallback_used = True
                    except Exception as fallback_exc:
                        logger.exception(f"Bot API fallback also failed for update to {update_channel}: {fallback_exc}")
                        raise exc
                else:
                    raise

            logger.info(
                f"Admin {message.from_user.id} published photo update to channel {update_channel} "
                f"{'with buttons' if include_buttons else 'without buttons'}"
                f"{' (fallback used)' if fallback_used else ''}"
            )

            if fallback_used:
                success_msg = (
                    f"✅ <b>Update Published via Fallback!</b>\n\n"
                    f"<b>Channel:</b> <code>{update_channel}</code>\n"
                    f"<i>The update text {'with links' if include_buttons else 'without links'} has been sent.</i>"
                )
            else:
                success_msg = (
                    f"✅ <b>Update Published!</b>\n\n"
                    f"<b>Channel:</b> <code>{update_channel}</code>\n"
                    f"<i>The image {'with buttons' if include_buttons else 'without buttons'} and sticker have been sent.</i>"
                )
            await message.reply(success_msg, parse_mode=enums.ParseMode.HTML)
        
        # ──── LINK MODE ────
        else:
            # Extract channel and message ID from link
            link_result = extract_channel_post_id(replied_message.text)
            print(f"Extracted from link: {link_result}")
            if not link_result:
                await message.reply("❌ Could not parse Telegram post link.")
                return
            
            channel_identifier, original_msg_id = link_result
            
            # Send reply to the linked post
            try:
                quoted_text = f"<blockquote>{reply_text}</blockquote>" if reply_text else "[Reply sent by admin]"
                await client.send_message(
                    chat_id=update_channel,
                    text=quoted_text,
                    parse_mode=enums.ParseMode.HTML,
                    reply_to_message_id=original_msg_id
                )
                logger.info(
                    f"Admin {message.from_user.id} published reply to post {original_msg_id} in channel {update_channel}"
                )
                success_msg = (
                    f"✅ <b>Reply Published!</b>\n\n"
                    f"<b>Channel:</b> <code>{update_channel}</code>\n"
                    f"<b>Reply to:</b> <code>{original_msg_id}</code>\n"
                    f"<i>Your reply has been sent to the post.</i>"
                )
                await message.reply(success_msg, parse_mode=enums.ParseMode.HTML)
            except Exception as exc:
                is_peer_error = (
                    (isinstance(exc, ValueError) and "Peer id invalid" in str(exc))
                    or isinstance(exc, PeerIdInvalid)
                )
                if is_peer_error:
                    logger.warning(f"Peer error sending reply to post {original_msg_id}, using fallback: {exc}")
                    try:
                        fallback_text = f"<blockquote>{reply_text}</blockquote>" if reply_text else "[Reply sent by admin]"
                        await botapi_send_message(client.bot_token, update_channel, fallback_text)
                        logger.info("Sent reply to %s using Bot API fallback", update_channel)
                        await message.reply(
                            f"✅ <b>Reply Published via Fallback!</b>\n\n"
                            f"<b>Channel:</b> <code>{update_channel}</code>\n"
                            f"<i>Your reply has been sent as a standalone message.</i>",
                            parse_mode=enums.ParseMode.HTML
                        )
                    except Exception as fallback_exc:
                        logger.exception(f"Bot API fallback also failed for reply to {update_channel}: {fallback_exc}")
                        raise exc
                else:
                    raise

        # Log to LOG_CHANNEL
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                user = message.from_user
                user_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
                username_str = f" (@{user.username})" if user.username else ""

                if is_photo_mode:
                    log_msg = (
                        f"📢 <b>Photo Update Published</b>\n\n"
                        f"<b>Admin:</b> {user_link}{username_str}\n"
                        f"<b>Admin ID:</b> <code>{user.id}</code>\n"
                        f"<b>Channel:</b> <code>{update_channel}</code>\n"
                        f"<b>With Buttons:</b> {'Yes' if include_buttons else 'No'}\n"
                        f"<b>Method:</b> {'Primary' if not fallback_used else 'Fallback'}"
                    )
                else:
                    log_msg = (
                        f"💬 <b>Reply Published</b>\n\n"
                        f"<b>Admin:</b> {user_link}{username_str}\n"
                        f"<b>Admin ID:</b> <code>{user.id}</code>\n"
                        f"<b>Channel:</b> <code>{update_channel}</code>\n"
                        f"<b>Reply to Post:</b> <code>{original_msg_id}</code>\n"
                        f"<b>Message:</b> <code>{html.escape(reply_text or '[No text]')}</code>"
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


@Client.on_callback_query(filters.regex(r"^emoji_"))
async def emoji_reaction_handler(client: Client, query):
    """Handle emoji reaction buttons (thumbs up, thumbs down, love)."""
    emoji_map = {
        "emoji_thumbs_up": "👍",
        "emoji_thumbs_down": "👎",
        "emoji_love": "❤️"
    }
    
    emoji = emoji_map.get(query.data, "👍")
    
    try:
        await query.answer(f"You reacted with {emoji}", show_alert=False)
    except Exception:
        logger.exception("Failed to answer emoji reaction callback")


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