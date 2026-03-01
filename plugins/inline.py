import logging

from pyrogram import Client, filters, emoji
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultCachedDocument,
    InlineQuery,
)
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid

from bot.config import settings
from bot.utils.cache import RuntimeCache
from bot.utils.helpers import is_subscribed, get_size
from database.ia_filterdb import get_search_results

logger = logging.getLogger(__name__)

INLINE_CACHE_TIME = settings.CACHE_TIME


async def inline_user_allowed(query: InlineQuery) -> bool:
    # only banned users are prevented from inline access; sudo/admins
    # automatically bypass bans by virtue of not being in the banned list.
    return bool(
        query.from_user
        and query.from_user.id not in RuntimeCache.banned_users
    )



@Client.on_inline_query()
async def inline_query_handler(client: Client, query: InlineQuery):
    """Handle inline search queries"""

    if not await inline_user_allowed(query):
        # likely a banned user
        return await query.answer(
            results=[],
            cache_time=0,
            switch_pm_text="🚫 You are not allowed to use this bot.",
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

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔍 Search again", switch_inline_query_current_chat=keyword)]]
    )

    files, next_offset, total = await get_search_results(
        keyword,
        file_type=file_type,
        max_results=10,
        offset=offset,
    )

    results = []

    for file in files:
        title = file.file_name
        size = get_size(file.file_size)
        caption = file.caption

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

        results.append(
            InlineQueryResultCachedDocument(
                title=title,
                document_file_id=file.file_id,
                caption=caption,
                description=f"Size: {size}\nType: {file.file_type}",
                reply_markup=reply_markup,
            )
        )

    if results:
        switch_pm_text = f"{emoji.FILE_FOLDER} Results — {total}"
        if keyword:
            switch_pm_text += f" for {keyword}"

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
        switch_pm_text = f"{emoji.CROSS_MARK} No results"
        if keyword:
            switch_pm_text += f' for "{keyword}"'

        await query.answer(
            results=[],
            is_personal=True,
            cache_time=INLINE_CACHE_TIME,
            switch_pm_text=switch_pm_text,
            switch_pm_parameter="okay",
        )