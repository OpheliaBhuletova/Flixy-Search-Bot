import logging
import re
import base64
from struct import pack
from typing import Tuple, List

from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from marshmallow.exceptions import ValidationError

from umongo import Instance, Document, fields
from datetime import datetime, timezone

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
    created_at = fields.DateTimeField(required=True)

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
            "created_at",
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
    _display_title = _announcement_key(file_name)
    try:
        file = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type = getattr(media, "mime_type", None),
            caption=media.caption.html if media.caption else None,
            created_at=datetime.now(timezone.utc),
        )
    except ValidationError:
        logger.exception("Validation error while saving media")
        return False, 2, _display_title or file_name

    try:
        await file.commit()
        return True, 1, _display_title or file_name
    except DuplicateKeyError:
        return False, 0, _display_title or file_name
    except Exception:
        logger.exception("Unexpected error while saving media")
        return False, 2, _display_title or file_name

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
    
    # Limit max fetch to avoid loading entire database into memory for broad queries
    MAX_MEMORY_RESULTS = 100
    if total_results > MAX_MEMORY_RESULTS:
        total_results = MAX_MEMORY_RESULTS

    next_offset = offset + max_results
    if next_offset >= total_results:
        next_offset = ""

    sort_field = "created_at" if not query else "_id"

    # Fetch up to MAX_MEMORY_RESULTS instead of just max_results for the current page
    cursor = (
        Media.find(mongo_filter)
        .sort(sort_field, -1)
        .limit(MAX_MEMORY_RESULTS)
    )

    all_files = await cursor.to_list(length=MAX_MEMORY_RESULTS)

    if query:
        query_lower = query.lower()

        exact_matches = []
        startswith_matches = []
        contains_matches = []
        other_matches = []

        for file in all_files:
            name = (file.file_name or "").strip().lower()

            if name == query_lower:
                exact_matches.append(file)
            elif name.startswith(query_lower):
                startswith_matches.append(file)
            elif query_lower in name:
                contains_matches.append(file)
            else:
                other_matches.append(file)

        def get_lang_rank(name: str) -> int:
            name = name.lower()
            if "malayalam" in name or "mal" in name: return 1
            if "tamil" in name or "tam" in name: return 2
            if "telugu" in name or "tel" in name: return 3
            if "hindi" in name or "hin" in name: return 4
            if "english" in name or "eng" in name: return 5
            return 6

        sort_key = lambda x: (get_lang_rank(x.file_name or ""), -x.file_size)
        
        exact_matches.sort(key=sort_key)
        startswith_matches.sort(key=sort_key)
        contains_matches.sort(key=sort_key)
        other_matches.sort(key=sort_key)

        all_files = exact_matches + startswith_matches + contains_matches + other_matches

    # Apply pagination in Python after global sorting
    files = all_files[offset : offset + max_results]

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
def _announcement_key(title: str) -> str:
    """Generate a stable key for title announcement tracking.

    The bot only broadcasts a given movie once, even if multiple versions
    of the same movie (different quality/size/etc.) are indexed.

    To do that, we only use the "Name (Year)" part of the title when
    available (e.g. "Subedaar (2026)").
    """

    if not title:
        return ""

    title = title.strip()
    match = re.search(r"\(\s*\d{4}\s*\)", title)
    if match:
        key = title[: match.end()]
    else:
        key = title

    # Normalize whitespace/case for stable comparisons.
    key = re.sub(r"\s+", " ", key).lower().strip()
    return key


async def announce_title(title: str) -> bool:
    """Return True if title not announced before, and record it.

    The bot uses a simplified key (name + year) for tracking announcements.
    This helps avoid re-broadcasting the same movie when different
    versions/qualities are indexed.

    For backwards-compatibility, we also consider the legacy full-title key
    used in past versions.
    """
    try:
        coll = get_db().announced_titles
        normalized = _announcement_key(title)
        legacy = title.strip()

        # Case-insensitive match to handle existing entries with different casing.
        normalized_query = {"_id": {"$regex": f"^{re.escape(normalized)}$", "$options": "i"}}
        legacy_query = {"_id": {"$regex": f"^{re.escape(legacy)}$", "$options": "i"}}

        # If already announced under the normalized key in any case variant, skip.
        if await coll.find_one(normalized_query):
            return False

        # Backwards-compatibility: if an older entry exists under the full title,
        # consider it already announced and keep the new normalized key too.
        if normalized != legacy and await coll.find_one(legacy_query):
            try:
                await coll.insert_one({"_id": normalized})
            except Exception:
                # If duplicate key error occurs (race condition), it's already been announced
                pass
            return False

        # Use replace_one with upsert to avoid duplicate key errors in race conditions
        result = await coll.replace_one(
            {"_id": normalized},
            {"_id": normalized},
            upsert=True
        )
        return result.matched_count == 0 or result.upserted_id is not None
    except Exception as e:
        logger.exception(f"Error announcing title '{title}': {e}")
        # On error, assume it's already announced to prevent repeated errors
        return False


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

def _display_title(title: str) -> str:
    if not title:
        return ""

    title = title.strip()
    match = re.search(r"\(\s*\d{4}\s*\)", title)
    if match:
        value = title[: match.end()]
    else:
        value = title

    return re.sub(r"\s+", " ", value).strip()