from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import settings

_client = None
_db = None

def get_db():
    global _client, _db

    if _client is None:
        _client = AsyncIOMotorClient(settings.DATABASE_URL)
        _db = _client[settings.DATABASE_NAME]

    return _db