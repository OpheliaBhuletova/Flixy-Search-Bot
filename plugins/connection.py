import logging

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import settings
from database.connections_mdb import (
    add_connection,
    all_connections,
    if_active,
    delete_connection,
)

logger = logging.getLogger(__name__)


@Client.on_message((filters.private | filters.group) & filters.command("connect"))
async def connect_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply(
            f"You are an anonymous admin. Use /connect {message.chat.id} in PM"
        )

    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        try:
            _, group_id = message.text.split(" ", 1)
        except ValueError:
            await message.reply_text(
                "<b>Enter in correct format!</b>\n\n"
                "<code>/connect group_id</code>\n\n"
                "<i>Get your Group ID by adding me to the group and using <code>/id</code></i>",
                quote=True,
            )
            return
    else:
        group_id = message.chat.id

    try:
        member = await client.get_chat_member(group_id, user_id)
        if (
            member.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
            and user_id not in settings.ADMINS
        ):
            await message.reply_text(
                "You must be an admin in the given group!",
                quote=True,
            )
            return
    except Exception as e:
        logger.exception(e)
        await message.reply_text(
            "Invalid Group ID!\n\nIf correct, make sure I'm present in your group.",
            quote=True,
        )
        return

    try:
        bot_status = await client.get_chat_member(group_id, "me")
        if bot_status.status != enums.ChatMemberStatus.ADMINISTRATOR:
            return await message.reply_text(
                "Please add me as an admin in the group.",
                quote=True,
            )

        chat = await client.get_chat(group_id)
        title = chat.title

        connected = await add_connection(str(group_id), str(user_id))
        if connected:
            await message.reply_text(
                f"Successfully connected to **{title}**.\n"
                "Now you can manage your group from my PM!",
                quote=True,
                parse_mode=enums.ParseMode.MARKDOWN,
            )
            if chat_type != enums.ChatType.PRIVATE:
                await client.send_message(
                    user_id,
                    f"Connected to **{title}**!",
                    parse_mode=enums.ParseMode.MARKDOWN,
                )
        else:
            await message.reply_text(
                "You're already connected to this chat!",
                quote=True,
            )
    except Exception as e:
        logger.exception(e)
        await message.reply_text(
            "An error occurred. Please try again later.",
            quote=True,
        )


@Client.on_message((filters.private | filters.group) & filters.command("disconnect"))
async def disconnect_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return await message.reply(
            f"You are an anonymous admin. Use /connect {message.chat.id} in PM"
        )

    if message.chat.type == enums.ChatType.PRIVATE:
        return await message.reply_text(
            "Use /connections to view or disconnect from groups.",
            quote=True,
        )

    group_id = message.chat.id

    member = await client.get_chat_member(group_id, user_id)
    if (
        member.status not in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
        and str(user_id) not in map(str, settings.ADMINS)
    ):
        return

    removed = await delete_connection(str(user_id), str(group_id))
    if removed:
        await message.reply_text(
            "Successfully disconnected from this chat.",
            quote=True,
        )
    else:
        await message.reply_text(
            "This chat isn't connected.\nUse /connect to connect.",
            quote=True,
        )


@Client.on_message(filters.private & filters.command("connections"))
async def connections_handler(client: Client, message: Message):
    user_id = message.from_user.id
    group_ids = await all_connections(str(user_id))

    if not group_ids:
        await message.reply_text(
            "There are no active connections.\nConnect to a group first.",
            quote=True,
        )
        return

    buttons = []
    for gid in group_ids:
        try:
            chat = await client.get_chat(int(gid))
            active = await if_active(str(user_id), str(gid))
            status = " - ACTIVE" if active else ""
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{chat.title}{status}",
                        callback_data=f"groupcb:{gid}:{status}",
                    )
                ]
            )
        except Exception:
            continue

    if buttons:
        await message.reply_text(
            "Your connected groups:\n\n",
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True,
        )
    else:
        await message.reply_text(
            "There are no active connections.\nConnect to a group first.",
            quote=True,
        )