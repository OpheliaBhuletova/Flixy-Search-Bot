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
    # ─── Connection ────────────────────────────────────────────────────
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
    CHANNELS: Optional[List[Union[int, str]]] = []  # Deprecated
    MOVIES_CHANNELS: List[Union[int, str]] = []
    SERIES_CHANNELS: List[Union[int, str]] = []
    AUTH_GROUPS: Optional[List[int]] = None
    AD_CHANNEL: List[Union[int, str]] = []
    UPDATES_CHANNEL: Union[int, str] = 0
    SUDO_USERS: List[Union[int, str]] = []

    # ─── Database ──────────────────────────────────────────────────────
    # Dual-cluster mode separates inline and PM search data into different clusters.
    ENABLE_MULTI_DB: bool = False
    
    # Inline cluster
    DATABASE_URL_INLINE: str
    DATABASE_NAME_INLINE: str = "Telegram_Inline"
    
    # PM cluster
    DATABASE_URL_PM: str
    DATABASE_NAME_PM: str = "Telegram_PM"

    # ─── Others ────────────────────────────────────────────────────────
    USE_CAPTION_FILTER: bool = False
    CACHE_TIME: int = 300
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
    def parse_list_fields(cls, v) -> List:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") or v.startswith("("):
                try:
                    parsed = ast.literal_eval(v)
                    return list(parsed) if isinstance(parsed, (list, tuple)) else []
                except (ValueError, SyntaxError):
                    pass
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
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
        return parse_bool(v, False)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

def build_log_string() -> str:
    log = "Customized Configurations:\n"
    log += "TMDb metadata enabled\n" if settings.METADATA_ENABLED else "TMDb metadata disabled\n"
    log += "Spell check enabled\n" if settings.SPELL_CHECK_REPLY else "Spell check disabled\n"
    if settings.MAX_LIST_ELM:
        log += f"MAX_LIST_ELM: {settings.MAX_LIST_ELM}\n"
    return log

LOG_STR = build_log_string()