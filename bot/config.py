from typing import List, Union, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator
import ast
import json


TRUE_VALUES = {"true", "yes", "1", "enable", "y"}
FALSE_VALUES = {"false", "no", "0", "disable", "n"}


def parse_bool(value: str | bool, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    value = value.lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


class Settings(BaseSettings):
    # ─── Bot information ───────────────────────────────────────────────
    SESSION: str = "Flixy_Search_Bot"
    USER_SESSION: str = "User_Bot"

    API_ID: int
    API_HASH: str
    BOT_TOKEN: str
    USERBOT_STRING_SESSION: Optional[str] = None

    # ─── Bot settings ──────────────────────────────────────────────────
    CACHE_TIME: int = 300
    USE_CAPTION_FILTER: bool = False
    PICS: List[str] = [
        "https://github.com/OpheliaBhuletova/Flixy-Search-Bot/blob/main/static/images/startup_image.jpg"
    ]

    # ─── Admins, Channels & Users ──────────────────────────────────────
    ADMINS: List[Union[int, str]] = []
    CHANNELS: List[Union[int, str]] = []  # Deprecated - kept for backward compatibility
    MOVIES_CHANNELS: List[Union[int, str]] = []  # Movies save to inline DB (moviesDB)
    SERIES_CHANNELS: List[Union[int, str]] = []  # Series save to PM DB (seriesDB)
    # previously supported AUTH_USERS/AUTH_CHANNEL settings have been removed;
    # sudo users now control private search access.  AUTH_GROUPS remains for
    # future use.
    AUTH_GROUPS: Optional[List[int]] = None

    # Ad channels: send periodic promotional message to these channel IDs
    AD_CHANNEL: List[Union[int, str]] = []

    # Updates channel: send published updates to this channel
    UPDATES_CHANNEL: Union[int, str] = 0

    # sudo users (super-users) bypass certain restrictions such as
    # subscription checks and bans; configured via environment.
    SUDO_USERS: List[Union[int, str]] = []

    # ─── Database ──────────────────────────────────────────────────────
    # Original single-cluster configuration (used when ENABLE_MULTI_DB=False)
    DATABASE_URL: str
    DATABASE_NAME: str = "Telegram"
    COLLECTION_NAME: str = "channel_files"

    # ─── Multi-Cluster Mode (Phase 1-5) ──────────────────────────────
    # Dual-cluster mode enables separation of inline and PM searches into
    # different MongoDB Atlas projects/clusters. This allows for:
    # - Separate free clusters for inline and PM (MongoDB Atlas limit)
    # - Different indexing strategies per cluster
    # - Targeted search results (inline from inline cluster, PM from PM cluster)
    # - Gradual rollout and easy rollback to single-cluster mode
    #
    # When ENABLE_MULTI_DB is False (default):
    #   - All searches use the single unified cluster (DATABASE_URL, DATABASE_NAME)
    #   - Backward compatible with existing deployments
    #   - Fallback functions automatically use single cluster
    #
    # When ENABLE_MULTI_DB is True:
    #   - Inline searches use DATABASE_URL_INLINE + DATABASE_NAME_INLINE
    #   - PM searches use DATABASE_URL_PM + DATABASE_NAME_PM
    #   - Indexing prompts user to select target database
    #   - Full dual-cluster separation with database routing
    ENABLE_MULTI_DB: bool = False  # Toggle dual-cluster mode (default: False for backward compatibility)
    
    # Inline searches cluster (MongoDB Atlas Project 1)
    DATABASE_URL_INLINE: Optional[str] = None  # MongoDB URL for inline cluster (fallback to DATABASE_URL if None)
    DATABASE_NAME_INLINE: str = "Telegram_Inline"  # Database name in inline cluster
    COLLECTION_NAME_INLINE: str = "channel_files"  # Collection in inline database
    
    # PM searches cluster (MongoDB Atlas Project 2)
    DATABASE_URL_PM: Optional[str] = None  # MongoDB URL for PM cluster (fallback to DATABASE_URL if None)
    DATABASE_NAME_PM: str = "Telegram_PM"  # Database name in PM cluster
    COLLECTION_NAME_PM: str = "channel_files"  # Collection in PM database

    # ─── Others ────────────────────────────────────────────────────────
    LOG_CHANNEL: int = 0
    SUPPORT_CHAT: str = "TitanHelpDesk"

    P_TTI_SHOW_OFF: bool = False
    IMDB: bool = True
    TMDB_API_KEY: Optional[str] = None
    SINGLE_BUTTON: bool = True

    CUSTOM_FILE_CAPTION: Optional[str] = None
    BATCH_FILE_CAPTION: Optional[str] = None

    IMDB_TEMPLATE: str = (
        "<b>🔍 Query:</b> {query}\n\n"
        "🎬 <b>Title:</b> <a href={url}>{title}</a>\n"
        "🎭 <b>Genres:</b> {genres}\n"
        "📆 <b>Year:</b> <a href={url}/releaseinfo>{year}</a>\n"
        "⭐ <b>IMDb Rating:</b> <a href={url}/ratings>{rating}</a> / 10"
    )
    @property
    def METADATA_TEMPLATE(self) -> str:
        return self.IMDB_TEMPLATE
    
    LONG_IMDB_DESCRIPTION: bool = False
    SPELL_CHECK_REPLY: bool = True
    MAX_LIST_ELM: Optional[int] = None
    INDEX_REQ_CHANNEL: Optional[int] = None
    FILE_STORE_CHANNEL: List[int] = []

    MELCOW_NEW_USERS: bool = False
    PROTECT_CONTENT: bool = False
    PUBLIC_FILE_STORE: bool = True

    # ─── Boolean compatibility ─────────────────────────────────────────
    @property
    def METADATA_ENABLED(self) -> bool:
        return bool(self.TMDB_API_KEY)
    
    @field_validator(
        "ADMINS",
        "CHANNELS", 
        "MOVIES_CHANNELS",
        "SERIES_CHANNELS",
        "AD_CHANNEL",
        "SUDO_USERS",
        "FILE_STORE_CHANNEL",
        mode="before",
    )
    @classmethod
    def parse_list_fields(cls, v):
        """Parse list fields from environment variables."""
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            try:
                # Try parsing as Python literal (handles lists, tuples, etc.)
                parsed = ast.literal_eval(v)
                if isinstance(parsed, (list, tuple)):
                    return list(parsed)
            except (ValueError, SyntaxError):
                pass
            try:
                # Try parsing as JSON
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return v if isinstance(v, list) else []
    
    @field_validator(
        "P_TTI_SHOW_OFF",
        "IMDB",
        "SINGLE_BUTTON",
        "LONG_IMDB_DESCRIPTION",
        "SPELL_CHECK_REPLY",
        "MELCOW_NEW_USERS",
        "PROTECT_CONTENT",
        "PUBLIC_FILE_STORE",
        mode="before",
    )
    @classmethod
    def validate_bools(cls, v, info):
        defaults = {
            "P_TTI_SHOW_OFF": False,
            "IMDB": False,
            "SINGLE_BUTTON": True,
            "LONG_IMDB_DESCRIPTION": False,
            "SPELL_CHECK_REPLY": True,
            "MELCOW_NEW_USERS": False,
            "PROTECT_CONTENT": False,
            "PUBLIC_FILE_STORE": True,
        }
        return parse_bool(v, defaults[info.field_name])

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

def build_log_string() -> str:
    log = "Current Customized Configurations:\n"
    log += "TMDb metadata enabled\n" if settings.METADATA_ENABLED else "TMDb metadata disabled\n"
    log += "Spell check enabled\n" if settings.SPELL_CHECK_REPLY else "Spell check disabled\n"
    log += (
        f"MAX_LIST_ELM set to {settings.MAX_LIST_ELM}\n"
        if settings.MAX_LIST_ELM
        else "MAX_LIST_ELM not set\n"
    )
    return log


LOG_STR = build_log_string()