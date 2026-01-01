from email.mime import message
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.cache import RuntimeCache
from database.users_chats_db import db
from bot.config import settings


async def banned_users(_, __, message: Message) -> bool:
    return (
        message.from_user is not None
        and message.from_user.id in RuntimeCache.banned_users
    )


banned_user = filters.create(banned_users)


async def disabled_chat(_, __, message: Message) -> bool:
    return message.chat.id in RuntimeCache.banned_chats


disabled_group = filters.create(disabled_chat)


@Client.on_message(filters.private & banned_user & filters.incoming)
async def ban_reply(client: Client, message: Message):
    # db is already imported
    ban = await db.get_ban_status(message.from_user.id)
    reason = ban.get("ban_reason", "No reason provided")

    await message.reply_text(
        f"🚫 **Access Denied**\n\n"
        f"You are banned from using this bot.\n"
        f"**Reason:** `{reason}`"
    )


@Client.on_message(filters.group & disabled_group & filters.incoming)
async def grp_bd(client: Client, message: Message):
    buttons = [[
        InlineKeyboardButton(
            text="Support",
            url=f"https://t.me/{settings.SUPPORT_CHAT}"
        )
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)

    chat_data = await db.get_chat(message.chat.id)

    reason = chat_data.get("reason", "No reason provided")

    sent = await message.reply_text(
        text=(
            "🚫 **Chat Restricted**\n\n"
            "My admins have restricted me from working here.\n"
            "Please contact support for more information.\n\n"
            f"**Reason:** `<code>{reason}</code>`"
        ),
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )

    try:
        await sent.pin()
    except Exception:
        pass

    await client.leave_chat(message.chat.id)