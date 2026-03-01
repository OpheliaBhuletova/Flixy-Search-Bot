import os
from typing import Dict, Any


class RuntimeCache:
    """In-memory runtime cache (non-persistent)."""

    banned_users: list[int] = []
    banned_chats: list[int] = []

    current: int = int(os.getenv("SKIP", 2))
    cancel: bool = False

    settings: Dict[int, Dict[str, Any]] = {}

    bot_username: str | None = None
    bot_name: str | None = None
    startup_time: Any = None
    index_skip: int = 0
    ad_enabled: bool = False