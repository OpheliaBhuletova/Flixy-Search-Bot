import os
import logging
from datetime import datetime

from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.errors.exceptions.bad_request_400 import (
    UserNotParticipant,
    MediaEmpty,
    PhotoInvalidDimensions,
    WebpageMediaEmpty,
)

from bot.config import settings
from bot.utils.helpers import extract_user, get_file_id, last_online
from bot.services.imdb_service import get_poster

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("id"))
async def show_id_handler(client: Client, message):
    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        user = message.from_user
        await message.reply_text(
            f"<b>➲ First Name:</b> {user.first_name}\n"
            f"<b>➲ Last Name:</b> {user.last_name or ''}\n"
            f"<b>➲ Username:</b> {user.username}\n"
            f"<b>➲ Telegram ID:</b> <code>{user.id}</code>\n"
            f"<b>➲ Data Centre:</b> <code>{user.dc_id or ''}</code>",
            quote=True,
        )
        return

    text = f"<b>➲ Chat ID:</b> <code>{message.chat.id}</code>\n"

    if message.reply_to_message:
        text += (
            "<b>➲ User ID:</b> "
            f"<code>{message.from_user.id if message.from_user else 'Anonymous'}</code>\n"
            "<b>➲ Replied User ID:</b> "
            f"<code>{message.reply_to_message.from_user.id if message.reply_to_message.from_user else 'Anonymous'}</code>\n"
        )
        file_info = get_file_id(message.reply_to_message)
    else:
        text += (
            "<b>➲ User ID:</b> "
            f"<code>{message.from_user.id if message.from_user else 'Anonymous'}</code>\n"
        )
        file_info = get_file_id(message)

    if file_info:
        text += f"<b>{file_info.message_type}:</b> <code>{file_info.file_id}</code>\n"

    await message.reply_text(text, quote=True)


@Client.on_message(filters.command("info"))
async def user_info_handler(client: Client, message):
    status = await message.reply("Fetching user info...")
    user_id, _ = extract_user(message)

    try:
        user = await client.get_users(user_id)
    except Exception as e:
        return await status.edit(str(e))

    info = (
        f"<b>➲ First Name:</b> {user.first_name}\n"
        f"<b>➲ Last Name:</b> {user.last_name or '<b>None</b>'}\n"
        f"<b>➲ Telegram ID:</b> <code>{user.id}</code>\n"
        f"<b>➲ Username:</b> @{user.username or 'None'}\n"
        f"<b>➲ Data Centre:</b> <code>{user.dc_id or 'N/A'}</code>\n"
        f"<b>➲ User Link:</b> "
        f"<a href='tg://user?id={user.id}'>Click Here</a>\n"
    )

    if message.chat.type in {enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL}:
        try:
            member = await message.chat.get_member(user.id)
            joined = (member.joined_date or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
            info += f"<b>➲ Joined:</b> <code>{joined}</code>\n"
        except UserNotParticipant:
            pass

    buttons = [[InlineKeyboardButton("🔐 Close", callback_data="close_data")]]
    markup = InlineKeyboardMarkup(buttons)

    if user.photo:
        path = await client.download_media(user.photo.big_file_id)
        await message.reply_photo(
            photo=path,
            caption=info,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
        )
        os.remove(path)
    else:
        await message.reply_text(
            info,
            reply_markup=markup,
            parse_mode=enums.ParseMode.HTML,
        )

    await status.delete()


@Client.on_message(filters.command(["imdb", "search"]))
async def imdb_search_handler(client: Client, message):
    if len(message.command) < 2:
        return await message.reply("Give me a movie / series name.")

    query = message.text.split(None, 1)[1]
    status = await message.reply("Searching IMDb...")

    movies = await get_poster(query, bulk=True)
    if not movies:
        return await status.edit("No results found.")

    buttons = [
        [
            InlineKeyboardButton(
                text=f"{m.get('title')} - {m.get('year')}",
                callback_data=f"imdb#{m.movieID}",
            )
        ]
        for m in movies
    ]

    await status.edit(
        "Here is what I found on IMDb",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@Client.on_callback_query(filters.regex("^imdb#"))
async def imdb_callback_handler(client: Client, callback: CallbackQuery):
    _, movie_id = callback.data.split("#", 1)
    imdb = await get_poster(movie_id, id=True)

    if not imdb:
        return await callback.answer("No data found.", show_alert=True)

    caption = settings.IMDB_TEMPLATE.format(**imdb, query=imdb["title"])
    buttons = [[InlineKeyboardButton(imdb["title"], url=imdb["url"])]]
    markup = InlineKeyboardMarkup(buttons)

    try:
        await callback.message.reply_photo(
            photo=imdb["poster"],
            caption=caption,
            reply_markup=markup,
        )
    except (MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty):
        fallback = imdb["poster"].replace(".jpg", "._V1_UX360.jpg")
        await callback.message.reply_photo(
            photo=fallback,
            caption=caption,
            reply_markup=markup,
        )
    except Exception as e:
        logger.exception(e)
        await callback.message.reply(
            caption,
            reply_markup=markup,
            disable_web_page_preview=False,
        )

    await callback.message.delete()
    await callback.answer()