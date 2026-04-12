import json
from ..models.database import Database
from .embedding import EmbeddingEngine


class Indexer:
    def __init__(self, db: Database, engine: EmbeddingEngine):
        self._db = db
        self._engine = engine

    async def index_activities(self, target_date: str) -> int:
        activities = await self._db.fetch_all(
            "SELECT * FROM activities WHERE date(timestamp) = ? AND category != 'idle'",
            (target_date,),
        )
        count = 0
        for a in activities:
            existing = await self._db.fetch_one(
                "SELECT rowid FROM embeddings WHERE source_type = 'activity' AND source_id = ?",
                (a["id"],),
            )
            if existing:
                continue
            text = self._activity_to_text(a)
            if not text.strip():
                continue
            vec = await self._engine.embed(text)
            await self._db.execute(
                "INSERT INTO embeddings (source_type, source_id, text_content, embedding) "
                "VALUES (?, ?, ?, ?)",
                ("activity", a["id"], text, json.dumps(vec)),
            )
            count += 1
        return count

    async def index_commits(self, target_date: str) -> int:
        commits = await self._db.fetch_all(
            "SELECT * FROM git_commits WHERE date = ?", (target_date,)
        )
        count = 0
        for c in commits:
            existing = await self._db.fetch_one(
                "SELECT rowid FROM embeddings WHERE source_type = 'git_commit' AND source_id = ?",
                (c["id"],),
            )
            if existing:
                continue
            text = f"{c['message']} {c.get('files_changed', '')}"
            vec = await self._engine.embed(text)
            await self._db.execute(
                "INSERT INTO embeddings (source_type, source_id, text_content, embedding) "
                "VALUES (?, ?, ?, ?)",
                ("git_commit", c["id"], text, json.dumps(vec)),
            )
            count += 1
        return count

    async def index_worklog(self, draft_id: int) -> None:
        draft = await self._db.fetch_one(
            "SELECT * FROM worklog_drafts WHERE id = ?", (draft_id,)
        )
        if not draft:
            return
        text = f"{draft['issue_key']} {draft['summary']}"
        vec = await self._engine.embed(text)
        await self._db.execute(
            "INSERT INTO embeddings (source_type, source_id, text_content, embedding) "
            "VALUES (?, ?, ?, ?)",
            ("worklog", draft_id, text, json.dumps(vec)),
        )

    def _activity_to_text(self, activity: dict) -> str:
        parts = []
        if activity.get("app_name"):
            parts.append(activity["app_name"])
        if activity.get("window_title"):
            parts.append(activity["window_title"])
        if activity.get("url"):
            parts.append(activity["url"])
        if activity.get("signals"):
            try:
                signals = json.loads(activity["signals"])
                if signals.get("ocr_text"):
                    parts.append(signals["ocr_text"][:500])
            except (json.JSONDecodeError, TypeError):
                pass
        return " ".join(parts)
