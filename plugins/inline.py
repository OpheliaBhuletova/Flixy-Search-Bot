import logging
from datetime import datetime, timezone

from pyrogram import Client, enums
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultCachedDocument,
    InlineQuery,
)
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid

from bot.config import settings
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import get_size, remove_file_extension
from database.ia_filterdb import get_inline_search_results_with_fallback

logger = logging.getLogger(__name__)

INLINE_CACHE_TIME = settings.CACHE_TIME


async def inline_user_allowed(query: InlineQuery) -> bool:
    # only banned users are prevented from inline access;
    # sudo/admins automatically bypass bans by virtue of not being in the banned list.
    return bool(
        query.from_user and query.from_user.id not in RuntimeCache.banned_users
    )


@Client.on_inline_query()
async def inline_query_handler(client: Client, query: InlineQuery):
    """Handle inline search queries"""
    if not await inline_user_allowed(query):
        return await query.answer(
            results=[],
            cache_time=0,
            switch_pm_text=" You are not allowed to use this bot.",
            switch_pm_parameter="unauthorized",
        )

    query_text = query.query.strip()
    offset = int(query.offset or 0)

    if "|" in query_text:
        keyword, file_type = map(str.strip, query_text.split("|", 1))
        file_type = file_type.lower()
    else:
        keyword = query_text
        file_type = None

    now_date = datetime.now(timezone.utc).date()

    reply_markup = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                text=" Search Again", 
                switch_inline_query_current_chat=keyword,
                style=enums.ButtonStyle.SUCCESS
            )
        ]]
    )

    files, next_offset, total = await get_inline_search_results_with_fallback(
        keyword,
        file_type=file_type,
        max_results=10,
        offset=offset,
    )

    results = []

    for file in files:
        title = file.get('file_name') if isinstance(file, dict) else file.file_name
        title = remove_file_extension(title)  # Remove file extension from display
        size = get_size(file.get('file_size') if isinstance(file, dict) else file.file_size)
        caption = file.get('caption') if isinstance(file, dict) else file.caption
        file_id = file.get('_id') if isinstance(file, dict) else file.file_id

        created_at = file.get('created_at') if isinstance(file, dict) else getattr(file, "created_at", None)
        is_new_today = created_at.date() == now_date if created_at else False

        if settings.CUSTOM_FILE_CAPTION:
            try:
                caption = settings.CUSTOM_FILE_CAPTION.format(
                    file_name=title or "",
                    file_size=size or "",
                    file_caption=caption or "",
                )
            except Exception as e:
                logger.exception(e)

        if not caption:
            caption = title

        description = f"Size: {size}\nType: {file.get('file_type') if isinstance(file, dict) else file.file_type}"
        results.append(
            InlineQueryResultCachedDocument(
                title=title,
                document_file_id=file_id,
                caption=caption,
                description=f"✨ Recently Added\n{description}" if is_new_today else description,
                reply_markup=reply_markup,
            )
        )

    if results:
        if keyword:
            switch_pm_text = f"🎬 Results for “{keyword}” • {total:,} Found"
        else:
            switch_pm_text = f"🎬 Explore Movies • {total:,} Available"

        try:
            await query.answer(
                results=results,
                is_personal=True,
                cache_time=INLINE_CACHE_TIME,
                next_offset=str(next_offset),
                switch_pm_text=switch_pm_text,
                switch_pm_parameter="start",
            )
        except QueryIdInvalid:
            pass
        except Exception as e:
            logger.exception(e)
    else:
        if keyword:
            switch_pm_text = (
                "😕 No matches found\n\n"
                "Try:\n"
                "• Different spelling\n"
                "• Shorter keywords\n"
                "• English titles\n\n"
                "🔎 Tap below to search again"
            )
        else:
            switch_pm_text = "😕 No movies available"

        await query.answer(
            results=[],
            is_personal=True,
            cache_time=INLINE_CACHE_TIME,
            switch_pm_text=switch_pm_text,
            switch_pm_parameter="okay",
        )