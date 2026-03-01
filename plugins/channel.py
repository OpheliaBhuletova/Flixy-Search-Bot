import asyncio

from pyrogram import Client, filters

from bot.utils.broadcast import new_movie_broadcast
from pyrogram.types import Message

from bot.config import settings
from database.ia_filterdb import save_file, announce_title


MEDIA_FILTER = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(settings.CHANNELS) & MEDIA_FILTER)
async def channel_media_handler(client: Client, message: Message):
    """
    Handles media messages from configured channels
    and saves them into the database.
    """
    media = None
    file_type = None

    for kind in ("document", "video", "audio"):
        media = getattr(message, kind, None)
        if media:
            file_type = kind
            break

    if not media:
        return

    media.file_type = file_type
    media.caption = message.caption

    saved, reason, title = await save_file(media)
    if saved and await announce_title(title):
        asyncio.create_task(new_movie_broadcast(client, title))