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
)
from bot.services.web_search import search_gagala

from bot.services.imdb_service import get_poster

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

    # reuse auto_filter implementation for private chats
    await auto_filter(client, message)


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

        if settings.AUTH_CHANNEL and not await is_subscribed(client, query):
            return await query.answer(
                url=f"https://t.me/{RuntimeCache.bot_username}?start={ident}_{file_id}"
            )

        try:
            await client.send_cached_media(
                query.from_user.id,
                file_id,
                caption=caption,
                protect_content=(ident == "filep"),
            )
            await query.answer("Sent in PM", show_alert=True)
        except UserIsBlocked:
            await query.answer("Unblock the bot first", show_alert=True)
        except PeerIdInvalid:
            await query.answer(
                url=f"https://t.me/{RuntimeCache.bot_username}?start={ident}_{file_id}"
            )
        return

    await query.answer()


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
        else f"Results for <b>{search}</b>\n\n<i>(Note: Files will be automatically deleted after 6hrs)</i>"
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