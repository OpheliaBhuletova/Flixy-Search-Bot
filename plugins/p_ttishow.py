import logging
from pyrogram import Client, filters, enums
import os
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
from bot.utils.helpers import get_size, get_settings, schedule_delete_message
from bot.utils.messages import Texts as Text

logger = logging.getLogger(__name__)


@Client.on_message(filters.new_chat_members & filters.group)
async def on_bot_added(client: Client, message):
    joined_ids = [u.id for u in message.new_chat_members]

    if RuntimeCache.bot_id in joined_ids:
        if not await db.get_chat(message.chat.id):
            total = await client.get_chat_members_count(message.chat.id)
            added_by = message.from_user.mention if message.from_user else "Anonymous"
            # LOG_CHANNEL feature removed: do not send bot-added notifications to logs channel
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
                    url="https://t.me/+w7aX0q-ex1U1NDc1",
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


@Client.on_message(filters.command("logs") & filters.user(settings.ADMINS))
async def logs_handler(client: Client, message):
    """Send recent error log contents to admins.

    If the log is small send as a message, otherwise send as a document.
    """
    log_path = os.path.join("logs", "flixy-bot.log")
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return await message.reply(f"Could not read log file: {e}")

    if not lines:
        return await message.reply("Log file is empty.")

    tail = "".join(lines[-500:])

    if len(tail) <= 4000:
        await message.reply(f"<pre>{tail}</pre>", parse_mode=enums.ParseMode.HTML)
        return

    tmp_name = "logs_tail.txt"
    try:
        with open(tmp_name, "w", encoding="utf-8") as f:
            f.write(tail)
        sent = await message.reply_document(tmp_name)
        if message.chat.type == enums.ChatType.PRIVATE:
            schedule_delete_message(client, sent.chat.id, sent.id)
    finally:
        try:
            os.remove(tmp_name)
        except Exception:
            pass


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
    total_users = await db.total_users_count()
    if total_users == 0:
        return await msg.edit(
            "📭 <b>No users found</b>\n\n"
            "There are currently no users registered with the bot.",
            parse_mode=enums.ParseMode.HTML,
        )

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
        sent = await message.reply_document("users.txt")
        if message.chat.type == enums.ChatType.PRIVATE:
            schedule_delete_message(client, sent.chat.id, sent.id)


@Client.on_message(filters.command(["chats", "channels"]) & filters.user(settings.ADMINS))
async def list_chats_handler(client: Client, message):
    cmd = message.command[0].lower() if message.command else "chats"
    msg = await message.reply("Fetching...")

    if cmd == "channels":
        items = settings.CHANNELS or []
        if not items:
            return await msg.edit(
                "📭 <b>No channels configured</b>\n\n"
                "No channels are set in the `CHANNELS` configuration. Add channels to the environment to enable indexing.",
                parse_mode=enums.ParseMode.HTML,
            )

        text = "Channels:\n\n"
        for ch in items:
            try:
                # Convert to int if it's a string
                ch_id = int(ch) if isinstance(ch, str) else ch
                chat = await client.get_chat(ch_id)
                # Use title as the primary source, with fallbacks
                if chat.title:
                    title = chat.title
                elif chat.username:
                    title = f"@{chat.username}"
                else:
                    title = f"Channel {ch_id}"
                cid = chat.id
            except Exception as e:
                logger.warning(f"Failed to get chat info for {ch}: {e}")
                title = str(ch)
                cid = ch
            text += f"Title: {title} | ID: {cid}\n"

        try:
            await msg.edit(text)
        except MessageTooLong:
            with open("channels.txt", "w") as f:
                f.write(text)
            sent = await message.reply_document("channels.txt")
            if message.chat.type == enums.ChatType.PRIVATE:
                schedule_delete_message(client, sent.chat.id, sent.id)
        return

    # default: /chats — list groups saved in DB via /connect
    total_chats = await db.total_chat_count()
    if total_chats == 0:
        return await msg.edit(
            "📭 <b>No connected groups</b>\n\n"
            "You haven't connected any groups yet. Go to a group where you're admin and use <code>/connect {group_id}</code> in the bot's PM.",
            parse_mode=enums.ParseMode.HTML,
        )

    await msg.edit_text("Fetching chats...")
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
        sent = await message.reply_document("chats.txt")
        if message.chat.type == enums.ChatType.PRIVATE:
            schedule_delete_message(client, sent.chat.id, sent.id)