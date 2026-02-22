import asyncio
import logging
import time
import datetime

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from database.users_chats_db import db
from bot.config import settings
from bot.utils.broadcast import broadcast_messages

logger = logging.getLogger(__name__)


def _progress_bar(percent: int, length: int = 10) -> str:
    """Return a simple block progress bar like █████░░░░░."""
    percent = max(0, min(100, percent))
    filled = round((percent / 100) * length)
    return "█" * filled + "░" * (length - filled)


def _fmt_duration(seconds: int) -> str:
    return str(datetime.timedelta(seconds=max(0, int(seconds))))


def _build_report_html(
    *,
    title: str,
    total: int,
    done: int,
    success: int,
    blocked: int,
    deleted: int,
    failed: int,
    duration_seconds: int | None = None,
) -> str:
    total = max(0, int(total))
    done = max(0, int(done))
    success = max(0, int(success))
    blocked = max(0, int(blocked))
    deleted = max(0, int(deleted))
    failed = max(0, int(failed))

    percent = int((done / total) * 100) if total else 0
    bar = _progress_bar(percent, length=10)

    # Status emoji based on health
    if total and done == total and failed == 0 and blocked == 0 and deleted == 0:
        status_emoji = "🟢"
        status_text = "All delivered"
    elif failed > 0:
        status_emoji = "🟡"
        status_text = "Completed with issues"
    else:
        status_emoji = "🔵"
        status_text = "In progress"

    duration_line = ""
    if duration_seconds is not None:
        duration_line = f"\n⏱ Duration: <b>{_fmt_duration(duration_seconds)}</b>"

    # Telegram HTML: keep it simple (b, i, pre, code, blockquote, br, a)
    return (
        f"<b>{title}</b>\n\n"
        f"{status_emoji} Status: <b>{percent}%</b> — {status_text}\n\n"
        f"<code>{bar} {percent}%</code>\n"
        f"<b>Summary:</b>\n"
        f"👥 Users Reached: <b>{total}</b>\n"
        f"✅ Completed: <b>{done}</b>/<b>{total}</b>"
        f"{duration_line}\n\n"
        f"<b>Delivery:</b>\n"
        f"✔ Delivered: <b>{success}</b>\n"
        f"🚫 Blocked: <b>{blocked}</b>\n"
        f"🗑 Deleted: <b>{deleted}</b>\n"
        f"❌ Failed: <b>{failed}</b>"
    )


@Client.on_message(
    filters.command("broadcast")
    & filters.user(settings.ADMINS)
    & filters.reply
)
async def broadcast_handler(client: Client, message: Message):
    users = await db.get_all_users()
    broadcast_msg = message.reply_to_message

    # Initial status card
    total_users = await db.total_users_count()
    done = success = blocked = deleted = failed = 0

    start_time = time.time()

    status = await message.reply_text(
        _build_report_html(
            title="📣 Broadcast Started",
            total=total_users,
            done=done,
            success=success,
            blocked=blocked,
            deleted=deleted,
            failed=failed,
            duration_seconds=0,
        ),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

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

        # Update every 20 users (same as your original)
        if done % 20 == 0:
            elapsed = int(time.time() - start_time)
            await status.edit_text(
                _build_report_html(
                    title="📣 Broadcast In Progress",
                    total=total_users,
                    done=done,
                    success=success,
                    blocked=blocked,
                    deleted=deleted,
                    failed=failed,
                    duration_seconds=elapsed,
                ),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    # Final report
    elapsed = int(time.time() - start_time)
    final_report = _build_report_html(
        title="📣 Broadcast Completed",
        total=total_users,
        done=done,
        success=success,
        blocked=blocked,
        deleted=deleted,
        failed=failed,
        duration_seconds=elapsed,
    )
    
    await status.edit_text(
        final_report,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    
    # Send copy to LOG_CHANNEL
    log_channel = getattr(settings, "LOG_CHANNEL", 0)
    if log_channel:
        try:
            await client.send_message(
                log_channel,
                final_report,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("Failed to send broadcast report to LOG_CHANNEL")