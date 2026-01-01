from pyrogram import Client, filters
from pyrogram.types import Message

from bot.config import settings
from database.ia_filterdb import save_file


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

    await save_file(media)