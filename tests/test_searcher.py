import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from auto_daily_log.models.database import Database
from auto_daily_log.search.indexer import Indexer
from auto_daily_log.search.searcher import Searcher


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db", embedding_dimensions=4)
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def mock_engine():
    engine = AsyncMock()
    engine.dimensions = 4
    async def fake_embed(text):
        if "coding" in text.lower() or "intellij" in text.lower():
            return [1.0, 0.0, 0.0, 0.0]
        elif "meeting" in text.lower() or "zoom" in text.lower():
            return [0.0, 1.0, 0.0, 0.0]
        else:
            return [0.5, 0.5, 0.0, 0.0]
    engine.embed = fake_embed
    return engine


@pytest.mark.asyncio
async def test_index_activity(db, mock_engine):
    await db.execute(
        "INSERT INTO activities (timestamp, app_name, window_title, category, confidence, duration_sec) "
        "VALUES ('2026-04-12T10:00:00', 'IntelliJ IDEA', 'Main.java', 'coding', 0.92, 3600)"
    )
    indexer = Indexer(db, mock_engine)
    count = await indexer.index_activities("2026-04-12")
    assert count == 1

    rows = await db.fetch_all("SELECT * FROM embeddings WHERE source_type = 'activity'")
    assert len(rows) == 1
    assert "IntelliJ" in rows[0]["text_content"]


@pytest.mark.asyncio
async def test_search_returns_ranked_results(db, mock_engine):
    await db.execute(
        "INSERT INTO activities (timestamp, app_name, window_title, category, confidence, duration_sec) "
        "VALUES ('2026-04-12T10:00:00', 'IntelliJ IDEA', 'Main.java', 'coding', 0.92, 3600)"
    )
    await db.execute(
        "INSERT INTO activities (timestamp, app_name, window_title, category, confidence, duration_sec) "
        "VALUES ('2026-04-12T11:00:00', 'Zoom', 'Sprint Meeting', 'meeting', 0.95, 1800)"
    )
    indexer = Indexer(db, mock_engine)
    await indexer.index_activities("2026-04-12")

    searcher = Searcher(db, mock_engine)
    results = await searcher.search("coding in IntelliJ", limit=2)
    assert len(results) == 2
    assert results[0]["source_type"] == "activity"
    assert "IntelliJ" in results[0]["text_content"]


@pytest.mark.asyncio
async def test_index_commits(db, mock_engine):
    await db.execute(
        "INSERT INTO git_repos (path, author_email, is_active) VALUES ('/tmp/repo', 'test@test.com', 1)"
    )
    await db.execute(
        "INSERT INTO git_commits (repo_id, hash, message, author, committed_at, files_changed, date) "
        "VALUES (1, 'abc', 'fix coding bug', 'test', '2026-04-12T10:30:00', '[\"Main.java\"]', '2026-04-12')"
    )
    indexer = Indexer(db, mock_engine)
    count = await indexer.index_commits("2026-04-12")
    assert count == 1


@pytest.mark.asyncio
async def test_no_duplicate_indexing(db, mock_engine):
    await db.execute(
        "INSERT INTO activities (timestamp, app_name, window_title, category, confidence, duration_sec) "
        "VALUES ('2026-04-12T10:00:00', 'IntelliJ IDEA', 'Main.java', 'coding', 0.92, 3600)"
    )
    indexer = Indexer(db, mock_engine)
    await indexer.index_activities("2026-04-12")
    await indexer.index_activities("2026-04-12")

    rows = await db.fetch_all("SELECT * FROM embeddings WHERE source_type = 'activity'")
    assert len(rows) == 1  # not duplicated
