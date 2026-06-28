from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import settings

_client_default = None
_db_default = None

# Dual cluster connections (used when ENABLE_MULTI_DB=True)
_client_inline = None
_db_inline = None
_client_pm = None
_db_pm = None

def get_db():
    """
    Get the default database instance used for general bot operations 
    (user stats, bans, settings). Routes to the PM cluster.
    """
    global _client_default, _db_default

    if _client_default is None:
        _client_default = AsyncIOMotorClient(
            settings.DATABASE_URL_PM,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            retryWrites=True,
            retryReads=True,
            maxPoolSize=50,
            minPoolSize=1,
            appname="FlixySearchBot",
        )
        _db_default = _client_default[settings.DATABASE_NAME_PM]

    return _db_default

def get_inline_db():
    """Get the dedicated database instance for inline searches."""
    global _client_inline, _db_inline

    if _client_inline is None:
        _client_inline = AsyncIOMotorClient(
            settings.DATABASE_URL_INLINE,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            retryWrites=True,
            retryReads=True,
            maxPoolSize=50,
            minPoolSize=1,
            appname="FlixySearchBot-Inline",
        )
        _db_inline = _client_inline[settings.DATABASE_NAME_INLINE]

    return _db_inline

def get_pm_db():
    """Get the dedicated database instance for PM searches."""
    global _client_pm, _db_pm

    if _client_pm is None:
        _client_pm = AsyncIOMotorClient(
            settings.DATABASE_URL_PM,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000,
            retryWrites=True,
            retryReads=True,
            maxPoolSize=50,
            minPoolSize=1,
            appname="FlixySearchBot-PM",
        )
        _db_pm = _client_pm[settings.DATABASE_NAME_PM]

    return _db_pm

def get_inline_collection():
    """Routes to the correct inline search collection based on mode."""
    if settings.ENABLE_MULTI_DB:
        return get_inline_db()["Cluster0"]
    return get_db()["Cluster0"]

def get_pm_collection():
    """Routes to the correct PM search collection based on mode."""
    if settings.ENABLE_MULTI_DB:
        return get_pm_db()["Cluster0"]
    return get_db()["Cluster0"]

def get_collection(db_type: str = "default"):
    """
    Helper to retrieve a specific collection by purpose.
    Defaults to PM collection for unspecified types.
    """
    if db_type == "inline":
        return get_inline_collection()
    if db_type == "pm":
        return get_pm_collection()
    return get_db()["Cluster0"]