from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import settings

_client = None
_db = None


def get_db():
    """Get the default database instance."""
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


def get_inline_collection():
    """Get the inline search collection."""
    db = get_db()
    if settings.ENABLE_MULTI_DB:
        return db[settings.COLLECTION_NAME_INLINE]
    else:
        return db[settings.COLLECTION_NAME]


def get_pm_collection():
    """Get the PM search collection."""
    db = get_db()
    if settings.ENABLE_MULTI_DB:
        return db[settings.COLLECTION_NAME_PM]
    else:
        return db[settings.COLLECTION_NAME]


def get_collection(db_type: str = "default"):
    """
    Get collection by type.
    
    Args:
        db_type: "inline", "pm", or "default"
    
    Returns:
        MongoDB collection instance
    """
    if db_type == "inline":
        return get_inline_collection()
    elif db_type == "pm":
        return get_pm_collection()
    else:
        return get_db()[settings.COLLECTION_NAME]