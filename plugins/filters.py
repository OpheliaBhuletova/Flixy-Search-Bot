import io

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.database.filters_mdb import (
    add_filter,
    get_filters,
    delete_filter,
    count_filters,
)
from bot.database.connections_mdb import active_connection
from bot.utils.media import get_file_id
from bot.utils.text import parser, split_quotes


@Client.on_message(filters.command(["filter", "add"]) & filters.incoming)
async def add_filter_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply(
            f"You are anonymous admin. Use /connect {message.chat.id} in PM"
        )

    chat_type = message.chat.type
    args = message.text.html.split(None, 1)

    if chat_type == enums.ChatType.PRIVATE:
        grp_id = await active_connection(str(user_id))
        if not grp_id:
            return await message.reply_text(
                "I'm not connected to any groups!", quote=True
            )
        chat = await client.get_chat(grp_id)
        title = chat.title
    else:
        grp_id = message.chat.id
        title = message.chat.title

    member = await client.get_chat_member(grp_id, user_id)
    if (
        member.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
        and str(user_id) not in map(str, settings.ADMINS)
    ):
        return

    if len(args) < 2:
        return await message.reply_text("Command incomplete :(", quote=True)

    extracted = split_quotes(args[1])
    keyword = extracted[0].lower()

    if not message.reply_to_message and len(extracted) < 2:
        return await message.reply_text(
            "Add some content to save your filter!", quote=True
        )

    try:
        if message.reply_to_message and message.reply_to_message.reply_markup:
            rm = message.reply_to_message.reply_markup
            buttons = rm.inline_keyboard
            msg = get_file_id(message.reply_to_message)
            file_id = msg.file_id if msg else None
            reply_text = (
                message.reply_to_message.caption.html
                if message.reply_to_message.caption
                else message.reply_to_message.text.html
            )
            alerts = None

        elif message.reply_to_message and message.reply_to_message.media:
            msg = get_file_id(message.reply_to_message)
            file_id = msg.file_id if msg else None
            reply_text, buttons, alerts = (
                parser(
                    message.reply_to_message.caption.html, keyword
                )
                if message.reply_to_message.caption
                else ("", [], None)
            )

        elif message.reply_to_message and message.reply_to_message.text:
            file_id = None
            reply_text, buttons, alerts = parser(
                message.reply_to_message.text.html, keyword
            )

        else:
            reply_text, buttons, alerts = parser(extracted[1], keyword)
            file_id = None

    except Exception:
        return await message.reply_text(
            "You cannot have buttons alone. Add some text!",
            quote=True,
        )

    await add_filter(grp_id, keyword, reply_text, buttons, file_id, alerts)

    await message.reply_text(
        f"Filter `{keyword}` added in **{title}**",
        quote=True,
        parse_mode=enums.ParseMode.MARKDOWN,
    )


@Client.on_message(filters.command(["viewfilters", "filters"]) & filters.incoming)
async def list_filters_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    if message.chat.type == enums.ChatType.PRIVATE:
        grp_id = await active_connection(str(user_id))
        if not grp_id:
            return await message.reply_text(
                "I'm not connected to any groups!", quote=True
            )
        chat = await client.get_chat(grp_id)
        title = chat.title
    else:
        grp_id = message.chat.id
        title = message.chat.title

    filters_list = await get_filters(grp_id)
    count = await count_filters(grp_id)

    if not count:
        return await message.reply_text(
            f"There are no active filters in **{title}**",
            quote=True,
            parse_mode=enums.ParseMode.MARKDOWN,
        )

    text = f"Total filters in **{title}** : {count}\n\n"
    for f in filters_list:
        text += f" × `{f}`\n"

    if len(text) > 4096:
        with io.BytesIO(text.replace("`", "").encode()) as f:
            f.name = "filters.txt"
            await message.reply_document(f, quote=True)
    else:
        await message.reply_text(
            text, quote=True, parse_mode=enums.ParseMode.MARKDOWN
        )