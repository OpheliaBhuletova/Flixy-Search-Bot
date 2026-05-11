from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import settings

# Single cluster connections (used when ENABLE_MULTI_DB=False)
_client_default = None
_db_default = None

# Dual cluster connections (used when ENABLE_MULTI_DB=True)
_client_inline = None
_db_inline = None
_client_pm = None
_db_pm = None


def get_db():
    """
    Get the default database instance.
    
    Used when ENABLE_MULTI_DB=False. This is the unified database for all operations.
    """
    global _client_default, _db_default

    if _client_default is None:
        _client_default = AsyncIOMotorClient(
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
        _db_default = _client_default[settings.DATABASE_NAME]

    return _db_default


def get_inline_db():
    """
    Get the inline database instance.
    
    Used when ENABLE_MULTI_DB=True. This is the dedicated cluster for inline searches.
    Falls back to default database if DATABASE_URL_INLINE is not configured.
    """
    global _client_inline, _db_inline

    if _client_inline is None:
        # Use dedicated inline cluster URL if provided, otherwise fallback to default
        url = settings.DATABASE_URL_INLINE or settings.DATABASE_URL
        _client_inline = AsyncIOMotorClient(
            url,
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
    """
    Get the PM database instance.
    
    Used when ENABLE_MULTI_DB=True. This is the dedicated cluster for PM searches.
    Falls back to default database if DATABASE_URL_PM is not configured.
    """
    global _client_pm, _db_pm

    if _client_pm is None:
        # Use dedicated PM cluster URL if provided, otherwise fallback to default
        url = settings.DATABASE_URL_PM or settings.DATABASE_URL
        _client_pm = AsyncIOMotorClient(
            url,
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
    """
    Get the inline search collection.
    
    Routes to:
    - Inline cluster collection if ENABLE_MULTI_DB=True
    - Default cluster collection if ENABLE_MULTI_DB=False
    """
    if settings.ENABLE_MULTI_DB:
        return get_inline_db()[settings.COLLECTION_NAME_INLINE]
    else:
        return get_db()[settings.COLLECTION_NAME]


def get_pm_collection():
    """
    Get the PM search collection.
    
    Routes to:
    - PM cluster collection if ENABLE_MULTI_DB=True
    - Default cluster collection if ENABLE_MULTI_DB=False
    """
    if settings.ENABLE_MULTI_DB:
        return get_pm_db()[settings.COLLECTION_NAME_PM]
    else:
        return get_db()[settings.COLLECTION_NAME]


def get_collection(db_type: str = "default"):
    """
    Get collection by type.
    
    Args:
        db_type: "inline", "pm", or "default"
        
        - "inline": Returns inline collection (inline cluster if ENABLE_MULTI_DB=True)
        - "pm": Returns PM collection (PM cluster if ENABLE_MULTI_DB=True)
        - "default": Returns default collection (primary cluster)
    
    Returns:
        MongoDB collection instance
    """
    if db_type == "inline":
        return get_inline_collection()
    elif db_type == "pm":
        return get_pm_collection()
    else:
        return get_db()[settings.COLLECTION_NAME]
