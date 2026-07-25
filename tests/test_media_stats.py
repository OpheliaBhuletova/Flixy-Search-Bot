import os

os.environ.setdefault("API_ID", "1")
os.environ.setdefault("API_HASH", "test-hash")
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL_INLINE", "mongodb://localhost")
os.environ.setdefault("DATABASE_URL_PM", "mongodb://localhost")

import pytest

from database import ia_filterdb


class _DummyCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=1):
        return self.docs


class _DummyCollection:
    def __init__(self, count, total_size):
        self.count = count
        self.total_size = total_size

    async def count_documents(self, query=None):
        return self.count

    def aggregate(self, pipeline):
        return _DummyCursor([{"total_size": self.total_size}])


@pytest.mark.asyncio
async def test_get_media_collection_stats_aggregates_multi_db_collections(monkeypatch):
    monkeypatch.setattr(ia_filterdb.settings, "ENABLE_MULTI_DB", True)
    monkeypatch.setattr(ia_filterdb, "get_inline_collection", lambda: _DummyCollection(3, 100))
    monkeypatch.setattr(ia_filterdb, "get_pm_collection", lambda: _DummyCollection(5, 200))

    count, total_size = await ia_filterdb.get_media_collection_stats()

    assert count == 8
    assert total_size == 300
