import logging
import re
import base64
from struct import pack
from typing import Tuple, List

from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from marshmallow.exceptions import ValidationError

from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient

from bot.config import settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

from database.mongo import get_db
from umongo import Instance

instance = Instance.from_db(get_db())


# ─── Media Document ──────────────────────────────────────────────────────
@instance.register
class Media(Document):
    file_id = fields.StrField(attribute="_id")
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        collection_name = settings.COLLECTION_NAME
        # MongoDB allows only one text index per collection. Use a compound
        # text index covering both file_name and caption fields. The
        # 'sparse' option cannot be applied to individual fields inside a
        # compound text index, so the caption document may be empty in some
        # records but that's fine for search.
        indexes = [
            {"key": [("file_name", "text"), ("caption", "text")]},
            "file_type",
        ]


# ─── Save Media ──────────────────────────────────────────────────────────
async def save_file(media) -> Tuple[bool, int, str]:
    """
    Store media document and return status plus normalized movie title.

    Returns:
        (True, 1, title)   → saved
        (False, 0, title)  → duplicate
        (False, 2, title)  → error
    """

    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"[_\-\.\+]", " ", str(media.file_name))

    try:
        file = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
    except ValidationError:
        logger.exception("Validation error while saving media")
        return False, 2

    try:
        await file.commit()
        return True, 1, file_name

    except DuplicateKeyError:
        return False, 0, file_name

    except Exception:
        logger.exception("Unexpected error while saving media")
        return False, 2, file_name


# ─── Search Engine ───────────────────────────────────────────────────────
async def get_search_results(
    query: str,
    file_type: str = None,
    max_results: int = 10,
    offset: int = 0,
    filter: bool = False,
):
    query = query.strip()

    if not query:
        pattern = ".*"
    elif " " not in query:
        pattern = rf"(\b|[.\+\-_]){re.escape(query)}(\b|[.\+\-_])"
    else:
        pattern = re.escape(query).replace(r"\ ", r".*[\s.\+\-_]")

    try:
        regex = re.compile(pattern, flags=re.IGNORECASE)
    except re.error:
        return [], "", 0

    if settings.USE_CAPTION_FILTER:
        mongo_filter = {"$or": [{"file_name": regex}, {"caption": regex}]}
    else:
        mongo_filter = {"file_name": regex}

    if file_type:
        mongo_filter["file_type"] = file_type

    total_results = await Media.count_documents(mongo_filter)
    next_offset = offset + max_results
    if next_offset >= total_results:
        next_offset = ""

    cursor = (
        Media.find(mongo_filter)
        .sort("_id", -1)
        .skip(offset)
        .limit(max_results)
    )

    files = await cursor.to_list(length=max_results)
    return files, next_offset, total_results


# ─── File Lookup ─────────────────────────────────────────────────────────
async def get_file_details(file_id: str) -> List[Media]:
    cursor = Media.find({"file_id": file_id})
    return await cursor.to_list(length=1)


# ─── Telegram File ID Encoding ───────────────────────────────────────────
def encode_file_id(data: bytes) -> str:
    result = b""
    zero_count = 0

    for byte in data + bytes([22, 4]):
        if byte == 0:
            zero_count += 1
        else:
            if zero_count:
                result += b"\x00" + bytes([zero_count])
                zero_count = 0
            result += bytes([byte])

    return base64.urlsafe_b64encode(result).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")



# ─── Announcement Tracking ─────────────────────────────────────────────
async def announce_title(title: str) -> bool:
    """Return True if title not announced before, and record it."""
    coll = get_db().announced_titles
    normalized = title.lower().strip()
    existing = await coll.find_one({"_id": normalized})
    if existing:
        return False
    await coll.insert_one({"_id": normalized})
    return True


def unpack_new_file_id(new_file_id: str) -> Tuple[str, str]:
    decoded = FileId.decode(new_file_id)

    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash,
        )
    )

    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref