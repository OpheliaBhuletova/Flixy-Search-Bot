import asyncio
import re
import ast
import math
import logging

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, MessageNotModified, PeerIdInvalid
from pyrogram.errors.exceptions.bad_request_400 import (
    MediaEmpty,
    PhotoInvalidDimensions,
    WebpageMediaEmpty,
)

from bot.config import settings

from database.connections_mdb import (
    active_connection,
    all_connections,
    delete_connection,
    if_active,
    make_active,
    make_inactive,
)
from database.users_chats_db import db
from database.ia_filterdb import (
    Media,
    get_file_details,
    get_search_results,
)
from database.filters_mdb import del_all, find_filter, get_filters
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import (
    get_size,
    is_subscribed,
    get_settings,
    save_group_settings,
    get_file_id,
    schedule_delete_message,
)
from bot.services.web_search import search_gagala

from bot.services.metadata_service import get_poster

logger = logging.getLogger(__name__)

BUTTONS: dict[str, str] = {}
SPELL_CHECK: dict[int, list[str]] = {}


# ---------------- GROUP MESSAGE HANDLER ---------------- #

@Client.on_message(filters.group & filters.text & filters.incoming)
async def group_message_router(client: Client, message):
    handled = await manual_filters(client, message)
    if handled is False:
        await auto_filter(client, message)


# ---------------- PRIVATE MESSAGE HANDLER ---------------- #

@Client.on_message(filters.private & filters.text & filters.incoming)
async def private_message_router(client: Client, message):
    """Handle plain-text movie requests in private chats.

    Treat non-command short messages as search queries and reuse the
    existing auto_filter logic so users get the same results in PM.
    """
    # ignore commands and long messages
    if message.text.startswith("/") or len(message.text) > 300:
        return

    # Only sudo users and admins can trigger PM movie searches.  Normal
    # users are directed to inline mode instead of receiving replies here.
    uid = message.from_user.id if message.from_user else None
    if uid and uid not in settings.SUDO_USERS and uid not in settings.ADMINS:
        return

    # reuse auto_filter implementation for private chats
    await auto_filter(client, message)


# -------- IMAGE FILE ID HANDLER IN PRIVATE MESSAGES -------- #

@Client.on_message(filters.private & filters.photo & filters.incoming)
async def pm_image_file_id_handler(client: Client, message):
    """Handle images sent to bot PM and log file IDs.
    
    When a user sends a photo or document to the bot, extract the file_id,
    print it to console logs, and send it to the configured LOG_CHANNEL.
    """
    file_info = get_file_id(message)
    
    if file_info:
        user = message.from_user
        user_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
        username_str = f" (@{user.username})" if user.username else ""
        
        # Log to console
        logger.info(
            f"Image received from user {user.id} ({user.first_name}): "
            f"File ID: {file_info.file_id} (Type: {file_info.message_type})"
        )
        
        # Send to LOG_CHANNEL if configured
        log_channel = getattr(settings, "LOG_CHANNEL", 0)
        if log_channel:
            try:
                log_message = (
                    f"<b>🖼️ Image File ID Received</b>\n\n"
                    f"<b>User:</b> {user_link}{username_str}\n"
                    f"<b>User ID:</b> <code>{user.id}</code>\n"
                    f"<b>Media Type:</b> <code>{file_info.message_type}</code>\n"
                    f"<b>File ID:</b> <code>{file_info.file_id}</code>"
                )
                await client.send_message(log_channel, log_message, parse_mode=enums.ParseMode.HTML)
            except Exception:
                logger.exception("Failed to send image file ID to LOG_CHANNEL")


@Client.on_message(filters.command("setstartup") & filters.user(settings.ADMINS) & filters.private)
async def set_startup_image(client: Client, message):
    """Set startup image from replied or attached photo (admin only)."""

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
        await message.reply(
            "✅ <b>Startup image updated!</b>",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        logger.exception("Error setting startup image from pm_filter")
        await message.reply(f"❌ Error: {str(e)}")


# ---------------- PAGINATION ---------------- #

@Client.on_callback_query(filters.regex(r"^next_"))
async def next_page(client: Client, query: CallbackQuery):
    _, req, key, offset = query.data.split("_")

    if int(req) not in {query.from_user.id, 0}:
        return await query.answer("Not authorized", show_alert=True)

    offset = int(offset) if offset.isdigit() else 0
    search = BUTTONS.get(key)

    if not search:
        return await query.answer("Old message expired", show_alert=True)

    files, next_offset, total = await get_search_results(
        search, offset=offset, filter=True
    )

    if not files:
        return await query.answer()

    settings_data = await get_settings(query.message.chat.id)
    secure = settings_data["file_secure"]
    pre = "filep" if secure else "file"

    buttons = []
    for file in files:
        if settings_data["button"]:
            buttons.append([
                InlineKeyboardButton(
                    f"[{get_size(file.file_size)}] {file.file_name}",
                    callback_data=f"{pre}#{file.file_id}",
                )
            ])
        else:
            buttons.append([
                InlineKeyboardButton(file.file_name, callback_data=f"{pre}#{file.file_id}"),
                InlineKeyboardButton(get_size(file.file_size), callback_data=f"{pre}#{file.file_id}"),
            ])

    page = math.ceil(offset / 10) + 1
    total_pages = math.ceil(total / 10)

    nav = []
    if offset > 0:
        nav.append(
            InlineKeyboardButton("⏪ BACK", callback_data=f"next_{req}_{key}_{offset-10}")
        )
    nav.append(
        InlineKeyboardButton(f"📃 {page}/{total_pages}", callback_data="pages")
    )
    if next_offset:
        nav.append(
            InlineKeyboardButton("NEXT ⏩", callback_data=f"next_{req}_{key}_{next_offset}")
        )

    buttons.append(nav)

    try:
        await query.edit_message_reply_markup(
            InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass

    await query.answer()


# ---------------- CALLBACK HANDLER ---------------- #

@Client.on_callback_query()
async def callback_router(client: Client, query: CallbackQuery):
    data = query.data

    if data == "close_data":
        await query.message.delete()
        return await query.answer()

    if data.startswith("file"):
        ident, file_id = data.split("#")
        files = await get_file_details(file_id)

        if not files:
            return await query.answer("File not found", show_alert=True)

        file = files[0]
        caption = file.caption or file.file_name
        size = get_size(file.file_size)

        if settings.CUSTOM_FILE_CAPTION:
            caption = settings.CUSTOM_FILE_CAPTION.format(
                file_name=file.file_name or "",
                file_size=size,
                file_caption=caption or "",
            )


        try:
            sent_msg = await client.send_cached_media(
                query.from_user.id,
                file_id,
                caption=caption,
                protect_content=(ident == "filep"),
            )
            await query.answer("Sent in PM", show_alert=True)

            # Schedule file deletion after 3 hours (10800 seconds)
            schedule_delete_message(client, sent_msg.chat.id, sent_msg.id, delay_seconds=10800)

            # Schedule reminder message at 2 hours 50 minutes (10200 seconds = 3hr - 10min)
            async def send_reminder():
                try:
                    reminder = await client.send_message(
                        query.from_user.id,
                        "⏰ <b>Reminder:</b> Your file will be deleted in 10 minutes.",
                        parse_mode=enums.ParseMode.HTML,
                    )
                    # Delete reminder message after 10 minutes
                    schedule_delete_message(client, reminder.chat.id, reminder.id, delay_seconds=600)
                except Exception as e:
                    logger.debug(f"Could not send reminder to {query.from_user.id}: {e}")

            # Schedule the reminder to be sent in 10200 seconds (2h 50min)
            asyncio.create_task(_schedule_task(send_reminder, 10200))

        except UserIsBlocked:
            await query.answer("Unblock the bot first", show_alert=True)
        except PeerIdInvalid:
            await query.answer(
                url=f"https://t.me/{RuntimeCache.bot_username}?start={ident}_{file_id}"
            )
        return

    await query.answer()


async def _schedule_task(coro_func, delay: int):
    """Schedule a coroutine function to run after delay seconds."""
    try:
        await asyncio.sleep(delay)
        await coro_func()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"Error in scheduled task: {e}")


# ---------------- AUTO FILTER ---------------- #

async def auto_filter(client: Client, message, spoll=None):
    settings_data = await get_settings(
        message.chat.id if not spoll else message.message.chat.id
    )

    if not spoll:
        if message.text.startswith("/") or len(message.text) > 100:
            return
        search = message.text.strip()
        files, offset, total = await get_search_results(search.lower(), filter=True)
        if not files:
            if settings_data["spell_check"]:
                return await spell_check(message)
            return
    else:
        search, files, offset, total = spoll
        message = message.message.reply_to_message

    pre = "filep" if settings_data["file_secure"] else "file"
    buttons = []

    for file in files:
        buttons.append([
            InlineKeyboardButton(
                f"[{get_size(file.file_size)}] {file.file_name}",
                callback_data=f"{pre}#{file.file_id}",
            )
        ])

    if offset:
        key = f"{message.chat.id}-{message.id}"
        BUTTONS[key] = search
        buttons.append([
            InlineKeyboardButton("🗓 1", callback_data="pages"),
            InlineKeyboardButton(
                "NEXT ⏩",
                callback_data=f"next_{message.from_user.id}_{key}_{offset}",
            ),
        ])

    imdb = await get_poster(search) if settings_data["imdb"] else None
    # Default caption for non-IMDB results: use HTML with a deletion note
    caption = (
        settings_data["template"].format(**imdb, query=search)
        if imdb
        else f"Results for <b>{search}</b>\n\n<i>(Note: Files will be automatically deleted after 3 hours)</i>"
    )

    if imdb and imdb.get("poster"):
        try:
            await message.reply_photo(
                imdb["poster"], caption[:1024], reply_markup=InlineKeyboardMarkup(buttons)
            )
        except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
            if not imdb:
                await message.reply_text(
                    caption,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode=enums.ParseMode.HTML,
                )
            else:
                await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        # When no IMDb/template is used, caption contains HTML and should be sent as HTML
        if not imdb:
            await message.reply_text(
                caption,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML,
            )
        else:
            await message.reply_text(caption, reply_markup=InlineKeyboardMarkup(buttons))


# ---------------- SPELL CHECK ---------------- #

async def spell_check(message):
    query = re.sub(r"\b(movie|file|send|pls|please)\b", "", message.text, flags=re.I)
    results = await search_gagala(query)

    if not results:
        await message.reply("No results found")
        return

    SPELL_CHECK[message.id] = results[:3]

    buttons = [
        [InlineKeyboardButton(title, callback_data=f"spolling#{message.from_user.id}#{i}")]
        for i, title in enumerate(results[:3])
    ]
    buttons.append([InlineKeyboardButton("Close", callback_data="close_data")])

    await message.reply(
        "Did you mean:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ---------------- MANUAL FILTERS ---------------- #

async def manual_filters(client: Client, message, text=None):
    group_id = message.chat.id
    content = text or message.text
    keywords = await get_filters(group_id)

    for keyword in sorted(keywords, key=len, reverse=True):
        if re.search(rf"\b{re.escape(keyword)}\b", content, re.I):
            reply_text, btn, alert, fileid = await find_filter(group_id, keyword)

            reply_text = reply_text.replace("\\n", "\n") if reply_text else ""
            markup = InlineKeyboardMarkup(ast.literal_eval(btn)) if btn not in ("[]", None) else None

            if fileid and fileid != "None":
                await message.reply_cached_media(fileid, caption=reply_text, reply_markup=markup)
            else:
                await message.reply(reply_text, reply_markup=markup)

            return True
    return False