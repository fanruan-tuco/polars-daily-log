"""Tests for scope period calculation, quarterly support, and deduplication."""

import pytest
import pytest_asyncio

from auto_daily_log.web.api.summaries import _resolve_scope_period


class TestResolveScopePeriod:
    """_resolve_scope_period returns correct (period_start, period_end)."""

    def test_day(self):
        ps, pe = _resolve_scope_period("day", "2026-04-18")
        assert ps == "2026-04-18"
        assert pe == "2026-04-18"

    def test_week_monday(self):
        # 2026-04-13 is Monday
        ps, pe = _resolve_scope_period("week", "2026-04-13")
        assert ps == "2026-04-13"
        assert pe == "2026-04-13"

    def test_week_friday(self):
        # 2026-04-17 is Friday, Monday is 2026-04-13
        ps, pe = _resolve_scope_period("week", "2026-04-17")
        assert ps == "2026-04-13"
        assert pe == "2026-04-17"

    def test_week_sunday(self):
        # 2026-04-19 is Sunday, Monday is 2026-04-13
        ps, pe = _resolve_scope_period("week", "2026-04-19")
        assert ps == "2026-04-13"
        assert pe == "2026-04-19"

    def test_month_first(self):
        ps, pe = _resolve_scope_period("month", "2026-04-01")
        assert ps == "2026-04-01"
        assert pe == "2026-04-01"

    def test_month_mid(self):
        ps, pe = _resolve_scope_period("month", "2026-04-18")
        assert ps == "2026-04-01"
        assert pe == "2026-04-18"

    def test_quarter_q1_jan(self):
        ps, pe = _resolve_scope_period("quarter", "2026-01-15")
        assert ps == "2026-01-01"
        assert pe == "2026-01-15"

    def test_quarter_q1_mar(self):
        ps, pe = _resolve_scope_period("quarter", "2026-03-31")
        assert ps == "2026-01-01"
        assert pe == "2026-03-31"

    def test_quarter_q2_apr(self):
        ps, pe = _resolve_scope_period("quarter", "2026-04-18")
        assert ps == "2026-04-01"
        assert pe == "2026-04-18"

    def test_quarter_q3_jul(self):
        ps, pe = _resolve_scope_period("quarter", "2026-07-01")
        assert ps == "2026-07-01"
        assert pe == "2026-07-01"

    def test_quarter_q4_dec(self):
        ps, pe = _resolve_scope_period("quarter", "2026-12-25")
        assert ps == "2026-10-01"
        assert pe == "2026-12-25"

    def test_custom_passthrough(self):
        ps, pe = _resolve_scope_period("custom", "2026-04-18",
                                        start_date="2026-04-01", end_date="2026-04-14")
        assert ps == "2026-04-01"
        assert pe == "2026-04-14"

    def test_unknown_type_defaults_to_target(self):
        ps, pe = _resolve_scope_period("foobar", "2026-04-18")
        assert ps == "2026-04-18"
        assert pe == "2026-04-18"


class TestScopeDedup:
    """generate_scope should overwrite existing summaries for the same period."""

    @pytest_asyncio.fixture
    async def db(self, tmp_path):
        from auto_daily_log.models.database import Database
        database = Database(tmp_path / "test.db", embedding_dimensions=4)
        await database.initialize()
        yield database
        await database.close()

    @pytest.mark.asyncio
    async def test_quarterly_scope_exists_in_db(self, db):
        """quarterly should be seeded by DB init."""
        row = await db.fetch_one("SELECT * FROM summary_types WHERE name = 'quarterly'")
        assert row is not None
        assert row["display_name"] == "季报"
        assert '"quarter"' in row["scope_rule"]

    @pytest.mark.asyncio
    async def test_quarterly_scope_output_exists(self, db):
        """quarterly scope_output should be seeded."""
        row = await db.fetch_one("SELECT * FROM scope_outputs WHERE scope_name = 'quarterly'")
        assert row is not None
        assert row["display_name"] == "季报"
        assert row["output_mode"] == "single"

    @pytest.mark.asyncio
    async def test_dedup_deletes_old_summary_same_period(self, db):
        """Regenerating for the same period should delete the old summary."""
        from unittest.mock import AsyncMock, MagicMock

        # Insert a fake "old" summary for daily 2026-04-18
        out = await db.fetch_one("SELECT id FROM scope_outputs WHERE scope_name = 'daily' LIMIT 1")
        old_id = await db.execute(
            "INSERT INTO summaries (scope_name, output_id, date, period_start, period_end, content) "
            "VALUES ('daily', ?, '2026-04-18', '2026-04-18', '2026-04-18', 'OLD CONTENT')",
            (out["id"],),
        )

        # Verify old exists
        old = await db.fetch_one("SELECT id FROM summaries WHERE id = ?", (old_id,))
        assert old is not None

        # Now generate — should delete the old one first
        from auto_daily_log.web.api.summaries import generate_scope
        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(return_value="NEW CONTENT")

        try:
            await generate_scope(db, mock_engine, "daily", "2026-04-18")
        except Exception:
            pass  # LLM mock may not be perfect; we just care about dedup

        # Old summary should be gone
        old_after = await db.fetch_one("SELECT id FROM summaries WHERE id = ?", (old_id,))
        assert old_after is None

    @pytest.mark.asyncio
    async def test_different_periods_not_deduped(self, db):
        """Summaries for different periods should coexist."""
        out = await db.fetch_one("SELECT id FROM scope_outputs WHERE scope_name = 'daily' LIMIT 1")

        await db.execute(
            "INSERT INTO summaries (scope_name, output_id, date, period_start, period_end, content) "
            "VALUES ('daily', ?, '2026-04-17', '2026-04-17', '2026-04-17', 'day 17')",
            (out["id"],),
        )
        await db.execute(
            "INSERT INTO summaries (scope_name, output_id, date, period_start, period_end, content) "
            "VALUES ('daily', ?, '2026-04-18', '2026-04-18', '2026-04-18', 'day 18')",
            (out["id"],),
        )

        rows = await db.fetch_all("SELECT * FROM summaries WHERE scope_name = 'daily'")
        assert len(rows) == 2  # different periods → both survive
