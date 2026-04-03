from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import settings

_client = None
_db = None


def get_db():
    global _client, _db

    if _client is None:
        _client = AsyncIOMotorClient(
            settings.DATABASE_URL,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            retryWrites=True,
            retryReads=True,
            maxPoolSize=50,
            minPoolSize=1,
            appname="FlixySearchBot",
        )
        _db = _client[settings.DATABASE_NAME]

    return _db