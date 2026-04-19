"""Thumbnail extraction utilities for documents and videos."""

import logging
import io
from typing import Optional, Any, BinaryIO

from pyrogram.client import Client
from pyrogram.types import Message, Document
from umongo import document

logger = logging.getLogger(__name__)


async def extract_thumbnail_from_document(
    client: Client,
    message: Message
) -> Optional[io.BytesIO]:
    """
    Extract and download thumbnail from a document or video.
    
    Args:
        client: Pyrogram Client instance
        message: Telegram message containing the document
        
    Returns:
        io.BytesIO object containing thumbnail data, or None if no thumbnail
    """
    try:
        # Check if message has a document with thumbnail
        media = message.document or message.video

        if not media:
            logger.warning("Message does not contain supported media")
            return None
        
        # Check if document has a thumbnail
        if not media.thumbs:
            logger.info(f"Document {media.file_name} has no thumbnail")
            return None
        
        # Get the largest thumbnail available
        thumb = max(media.thumbs, key=lambda x: x.width * x.height)
        
        # Download thumbnail using file_id
        thumb_bytes: str | BinaryIO | None = await client.download_media(thumb.file_id, in_memory=True)
        
        if isinstance(thumb_bytes, bytes):
            return io.BytesIO(thumb_bytes)
        
        # If it's a file path, read it
        if isinstance(thumb_bytes, str):
            with open(thumb_bytes, 'rb') as f:
                return io.BytesIO(f.read())
        
        return None
        
    except Exception as e:
        logger.exception(f"Error extracting thumbnail: {e}")
        return None


async def get_document_info(message: Message) -> dict[str, Any]:
    """
    Extract document information from a message.
    
    Args:
        message: Telegram message containing the document
        
    Returns:
        Dictionary with document information
    """
    if not message.document:
        return {}
    
    doc = message.document
    
    info: dict[str, Any] = {
        "file_name": doc.file_name or "Unknown",
        "file_size": doc.file_size or 0,
        "mime_type": doc.mime_type or "Unknown",
        "file_id": doc.file_id,
        "has_thumbnail": bool(doc.thumbs),
    }
    
    if doc.thumbs:
        largest_thumb = max(doc.thumbs, key=lambda x: x.width * x.height)
        info["thumbnail_dimensions"] = f"{largest_thumb.width}x{largest_thumb.height}"
    
    return info
