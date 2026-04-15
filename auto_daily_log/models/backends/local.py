"""Local SQLite storage backend — used by server's built-in collector."""
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.schemas import ActivityPayload, CommitPayload

from ..database import Database
from .base import StorageBackend


class LocalSQLiteBackend(StorageBackend):
    """Writes straight to the shared Database instance."""

    def __init__(self, db: Database):
        self._db = db

    async def save_activities(self, machine_id: str, activities: list[ActivityPayload]) -> list[int]:
        ids: list[int] = []
        for a in activities:
            row_id = await self._db.execute(
                """INSERT INTO activities
                   (timestamp, app_name, window_title, category, confidence,
                    url, signals, duration_sec, machine_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    a.timestamp, a.app_name, a.window_title, a.category,
                    a.confidence, a.url, a.signals, a.duration_sec, machine_id,
                ),
            )
            ids.append(row_id)
        return ids

    async def save_commits(self, machine_id: str, commits: list[CommitPayload]) -> int:
        inserted = 0
        for c in commits:
            # Dedupe by (repo_path, hash, machine_id)
            existing = await self._db.fetch_one(
                "SELECT id FROM git_commits WHERE hash = ? AND machine_id = ?",
                (c.hash, machine_id),
            )
            if existing:
                continue
            await self._db.execute(
                """INSERT INTO git_commits
                   (hash, message, author, committed_at, files_changed,
                    insertions, deletions, date, machine_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c.hash, c.message, c.author, c.committed_at, c.files_changed,
                    c.insertions, c.deletions, c.date, machine_id,
                ),
            )
            inserted += 1
        return inserted

    async def heartbeat(self, machine_id: str) -> Optional[dict]:
        # Update last_seen if collector exists in table (built-in machine_id='local'
        # is not registered by default but we can still touch it idempotently).
        await self._db.execute(
            "UPDATE collectors SET last_seen = datetime('now') WHERE machine_id = ?",
            (machine_id,),
        )

        # Mirror the old MonitorService runtime-config behaviour: surface a
        # settings-table override so the built-in CollectorRuntime picks up
        # UI changes (ocr_enabled, interval_sec…) without a restart. Only
        # the 'local' built-in reads this; standalone collectors use the
        # HTTP heartbeat which goes through a different code path.
        if machine_id != "local":
            return None

        rows = await self._db.fetch_all(
            "SELECT key, value FROM settings WHERE key IN "
            "('monitor_ocr_enabled', 'monitor_ocr_engine', 'monitor_interval_sec')"
        )
        s = {r["key"]: r["value"] for r in rows}
        if not s:
            return None

        def _bool(val: Optional[str]) -> Optional[bool]:
            if val is None:
                return None
            return str(val).lower() in ("true", "1", "yes", "on")

        override: dict = {}
        if "monitor_ocr_enabled" in s:
            override["ocr_enabled"] = _bool(s["monitor_ocr_enabled"])
        if "monitor_ocr_engine" in s and s["monitor_ocr_engine"]:
            override["ocr_engine"] = s["monitor_ocr_engine"]
        if "monitor_interval_sec" in s and s["monitor_interval_sec"]:
            try:
                override["interval_sec"] = int(s["monitor_interval_sec"])
            except (TypeError, ValueError):
                pass

        if not override:
            return None
        return {"config_override": override, "is_paused": False}

    async def extend_duration(self, machine_id: str, row_id: int, extra_sec: int) -> None:
        await self._db.execute(
            "UPDATE activities SET duration_sec = duration_sec + ? "
            "WHERE id = ? AND machine_id = ?",
            (extra_sec, row_id, machine_id),
        )

    async def save_screenshot(self, machine_id: str, local_path: Path) -> str:
        # Built-in collector writes screenshots straight into the server's
        # screenshot dir, so the path is already canonical.
        return str(local_path)
