from typing import List, Union, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


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
    CHANNELS: List[Union[int, str]] = []
    AUTH_USERS: List[Union[int, str]] = []
    AUTH_CHANNEL: Optional[Union[int, str]] = None
    AUTH_GROUPS: Optional[List[int]] = None

    # ─── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str
    DATABASE_NAME: str = "Telegram"
    COLLECTION_NAME: str = "channel_files"

    # ─── Others ────────────────────────────────────────────────────────
    LOG_CHANNEL: int = 0
    SUPPORT_CHAT: str = "TitanHelpDesk"

    P_TTI_SHOW_OFF: bool = False
    IMDB: bool = True
    SINGLE_BUTTON: bool = True

    CUSTOM_FILE_CAPTION: Optional[str] = None
    BATCH_FILE_CAPTION: Optional[str] = None

    IMDB_TEMPLATE: str = (
        "<b>Query: {query}</b>\n\n"
        "🏷 Title: <a href={url}>{title}</a>\n"
        "🎭 Genres: {genres}\n"
        "📆 Year: <a href={url}/releaseinfo>{year}</a>\n"
        "🌟 Rating: <a href={url}/ratings>{rating}</a> / 10"
    )

    LONG_IMDB_DESCRIPTION: bool = False
    SPELL_CHECK_REPLY: bool = True
    MAX_LIST_ELM: Optional[int] = None
    INDEX_REQ_CHANNEL: Optional[int] = None
    FILE_STORE_CHANNEL: List[int] = []

    MELCOW_NEW_USERS: bool = False
    PROTECT_CONTENT: bool = False
    PUBLIC_FILE_STORE: bool = True

    # ─── Boolean compatibility ─────────────────────────────────────────
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
    log += "IMDB enabled\n" if settings.IMDB else "IMDB disabled\n"
    log += "Spell check enabled\n" if settings.SPELL_CHECK_REPLY else "Spell check disabled\n"
    log += (
        f"MAX_LIST_ELM set to {settings.MAX_LIST_ELM}\n"
        if settings.MAX_LIST_ELM
        else "MAX_LIST_ELM not set\n"
    )
    return log


LOG_STR = build_log_string()