import asyncio
import time
import datetime

from pyrogram import Client, filters
from pyrogram.types import Message

from database.users_chats_db import db

from bot.config import settings
from bot.utils.broadcast import broadcast_messages


@Client.on_message(
    filters.command("broadcast")
    & filters.user(settings.ADMINS)
    & filters.reply
)
async def broadcast_handler(client: Client, message: Message):
    db = get_db()
    users = await db.get_all_users()
    broadcast_msg = message.reply_to_message

    status = await message.reply_text("📣 **Broadcast started...**")
    start_time = time.time()

    total_users = await db.total_users_count()
    done = success = blocked = deleted = failed = 0

    async for user in users:
        ok, reason = await broadcast_messages(int(user["id"]), broadcast_msg)

        if ok:
            success += 1
        else:
            if reason == "Blocked":
                blocked += 1
            elif reason == "Deleted":
                deleted += 1
            else:
                failed += 1

        done += 1
        await asyncio.sleep(2)

        if done % 20 == 0:
            await status.edit_text(
                f"📣 **Broadcast in progress**\n\n"
                f"👥 Total Users: {total_users}\n"
                f"✅ Completed: {done}/{total_users}\n"
                f"✔️ Success: {success}\n"
                f"🚫 Blocked: {blocked}\n"
                f"🗑 Deleted: {deleted}"
            )

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))

    await status.edit_text(
        f"📣 **Broadcast completed**\n\n"
        f"⏱ Time Taken: `{time_taken}`\n\n"
        f"👥 Total Users: {total_users}\n"
        f"✅ Completed: {done}/{total_users}\n"
        f"✔️ Success: {success}\n"
        f"🚫 Blocked: {blocked}\n"
        f"🗑 Deleted: {deleted}"
    )