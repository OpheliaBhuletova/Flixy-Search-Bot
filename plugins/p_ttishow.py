from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import ChatAdminRequired
from pyrogram.errors.exceptions.bad_request_400 import (
    MessageTooLong,
    PeerIdInvalid,
)

from bot.config import settings
from database.users_chats_db import db
from database.ia_filterdb import Media
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import get_size, get_settings
from bot.utils.messages import Text


@Client.on_message(filters.new_chat_members & filters.group)
async def on_bot_added(client: Client, message):
    joined_ids = [u.id for u in message.new_chat_members]

    if RuntimeCache.bot_id in joined_ids:
        if not await db.get_chat(message.chat.id):
            total = await client.get_chat_members_count(message.chat.id)
            added_by = message.from_user.mention if message.from_user else "Anonymous"
            await client.send_message(
                settings.LOG_CHANNEL,
                Text.LOG_TEXT_G.format(
                    message.chat.title, message.chat.id, total, added_by
                ),
            )
            await db.add_chat(message.chat.id, message.chat.title)

        if message.chat.id in RuntimeCache.banned_chats:
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Support", url=f"https://t.me/{settings.SUPPORT_CHAT}")]]
            )
            msg = await message.reply(
                "<b>CHAT NOT ALLOWED 🐞\n\n"
                "My admins have restricted me from working here.</b>",
                reply_markup=markup,
            )
            try:
                await msg.pin()
            except Exception:
                pass
            await client.leave_chat(message.chat.id)
            return

        markup = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(
                    "ℹ️ Help",
                    url=f"https://t.me/{RuntimeCache.bot_username}?start=help",
                ),
                InlineKeyboardButton(
                    "📢 Updates",
                    url="https://t.me/TitanBotUpdates",
                ),
            ]]
        )
        await message.reply_text(
            f"<b>Thank you for adding me to {message.chat.title} ❣️</b>",
            reply_markup=markup,
        )
        return

    settings_data = await get_settings(message.chat.id)
    if settings_data.get("welcome"):
        for user in message.new_chat_members:
            prev = RuntimeCache.welcome_cache.get("welcome")
            if prev:
                try:
                    await prev.delete()
                except Exception:
                    pass
            RuntimeCache.welcome_cache["welcome"] = await message.reply(
                f"<b>Hey {user.mention}, welcome to {message.chat.title}</b>"
            )


@Client.on_message(filters.command("leave") & filters.user(settings.ADMINS))
async def leave_chat_handler(client: Client, message):
    if len(message.command) < 2:
        return await message.reply("Give me a chat ID")

    chat = message.command[1]
    try:
        chat = int(chat)
    except ValueError:
        pass

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Support", url=f"https://t.me/{settings.SUPPORT_CHAT}")]]
    )
    await client.send_message(
        chat,
        "<b>My admin asked me to leave this group.</b>",
        reply_markup=markup,
    )
    await client.leave_chat(chat)
    await message.reply(f"Left chat `{chat}`")


@Client.on_message(filters.command("disable") & filters.user(settings.ADMINS))
async def disable_chat_handler(client: Client, message):
    if len(message.command) < 2:
        return await message.reply("Give me a chat ID")

    chat = int(message.command[1])
    reason = " ".join(message.command[2:]) or "No reason provided"

    chat_data = await db.get_chat(chat)
    if not chat_data:
        return await message.reply("Chat not found in database")

    if chat_data["is_disabled"]:
        return await message.reply(
            f"Chat already disabled.\nReason: <code>{chat_data['reason']}</code>"
        )

    await db.disable_chat(chat, reason)
    RuntimeCache.banned_chats.add(chat)

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Support", url=f"https://t.me/{settings.SUPPORT_CHAT}")]]
    )
    await client.send_message(
        chat,
        f"<b>This chat has been disabled.</b>\nReason: <code>{reason}</code>",
        reply_markup=markup,
    )
    await client.leave_chat(chat)
    await message.reply("Chat successfully disabled")


@Client.on_message(filters.command("enable") & filters.user(settings.ADMINS))
async def enable_chat_handler(client: Client, message):
    if len(message.command) < 2:
        return await message.reply("Give me a chat ID")

    chat = int(message.command[1])
    chat_data = await db.get_chat(chat)

    if not chat_data or not chat_data.get("is_disabled"):
        return await message.reply("Chat is not disabled")

    await db.re_enable_chat(chat)
    RuntimeCache.banned_chats.discard(chat)
    await message.reply("Chat successfully re-enabled")


@Client.on_message(filters.command("stats"))
async def stats_handler(client: Client, message):
    msg = await message.reply("Fetching stats...")
    users = await db.total_users_count()
    chats = await db.total_chat_count()
    files = await Media.count_documents()
    size = await db.get_db_size()
    free = get_size(536870912 - size)

    await msg.edit(
        Text.STATUS_TXT.format(
            files, users, chats, get_size(size), free
        )
    )


@Client.on_message(filters.command("ban") & filters.user(settings.ADMINS))
async def ban_user_handler(client: Client, message):
    if len(message.command) < 2:
        return await message.reply("Give me a user ID or username")

    target = message.command[1]
    reason = " ".join(message.command[2:]) or "No reason provided"

    user = await client.get_users(target)
    status = await db.get_ban_status(user.id)

    if status["is_banned"]:
        return await message.reply(f"{user.mention} is already banned")

    await db.ban_user(user.id, reason)
    RuntimeCache.banned_users.add(user.id)
    await message.reply(f"Successfully banned {user.mention}")


@Client.on_message(filters.command("unban") & filters.user(settings.ADMINS))
async def unban_user_handler(client: Client, message):
    if len(message.command) < 2:
        return await message.reply("Give me a user ID or username")

    target = message.command[1]
    user = await client.get_users(target)
    status = await db.get_ban_status(user.id)

    if not status["is_banned"]:
        return await message.reply("User is not banned")

    await db.remove_ban(user.id)
    RuntimeCache.banned_users.discard(user.id)
    await message.reply(f"Successfully unbanned {user.mention}")


@Client.on_message(filters.command("users") & filters.user(settings.ADMINS))
async def list_users_handler(client: Client, message):
    msg = await message.reply("Fetching users...")
    users = await db.get_all_users()
    text = "Users:\n\n"

    async for user in users:
        text += f"<a href='tg://user?id={user['id']}'>{user['name']}</a>"
        if user["ban_status"]["is_banned"]:
            text += " (Banned)"
        text += "\n"

    try:
        await msg.edit(text)
    except MessageTooLong:
        with open("users.txt", "w") as f:
            f.write(text)
        await message.reply_document("users.txt")


@Client.on_message(filters.command("chats") & filters.user(settings.ADMINS))
async def list_chats_handler(client: Client, message):
    msg = await message.reply("Fetching chats...")
    chats = await db.get_all_chats()
    text = "Chats:\n\n"

    async for chat in chats:
        text += f"Title: {chat['title']} | ID: {chat['id']}"
        if chat["chat_status"]["is_disabled"]:
            text += " (Disabled)"
        text += "\n"

    try:
        await msg.edit(text)
    except MessageTooLong:
        with open("chats.txt", "w") as f:
            f.write(text)
        await message.reply_document("chats.txt")