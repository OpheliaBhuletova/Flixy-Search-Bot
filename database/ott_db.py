import logging
import ast # For literal_eval
from umongo import Instance, Document, fields
from database.mongo import get_db # Assuming this exists and returns a Motor database client

logger = logging.getLogger(__name__)

instance = Instance.from_db(get_db())

@instance.register
class OTTMessage(Document):
    _id = fields.StrField(required=True) # Month name, e.g., "january"
    text = fields.StrField(allow_none=True)
    buttons = fields.StrField(allow_none=True) # Stored as string representation of list of lists of dicts
    file_id = fields.StrField(allow_none=True) # File ID if message is media
    
    class Meta:
        collection_name = "ott_messages"

async def get_ott_message(month: str):
    """Retrieve OTT message data for a given month."""
    return await OTTMessage.find_one({"_id": month.lower()})

async def set_ott_message(month: str, text: str, buttons: str = None, file_id: str = None):
    """Set or update OTT message data for a given month."""
    await OTTMessage.collection.update_one(
        {"_id": month.lower()},
        {"$set": {"text": text, "buttons": buttons, "file_id": file_id}},
        upsert=True
    )

async def ensure_ott_indexes():
    """Ensure indexes for the OTTMessage collection."""
    await OTTMessage.ensure_indexes()