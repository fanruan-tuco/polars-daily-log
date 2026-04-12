import json
from typing import Optional
from ..models.database import Database
from .embedding import EmbeddingEngine


class Searcher:
    def __init__(self, db: Database, engine: EmbeddingEngine):
        self._db = db
        self._engine = engine

    async def search(
        self, query: str, limit: int = 20, source_type: Optional[str] = None,
    ) -> list[dict]:
        query_vec = await self._engine.embed(query)

        if source_type:
            rows = await self._db.fetch_all(
                "SELECT source_type, source_id, text_content, distance "
                "FROM embeddings WHERE embedding MATCH ? AND source_type = ? "
                "ORDER BY distance LIMIT ?",
                (json.dumps(query_vec), source_type, limit),
            )
        else:
            rows = await self._db.fetch_all(
                "SELECT source_type, source_id, text_content, distance "
                "FROM embeddings WHERE embedding MATCH ? "
                "ORDER BY distance LIMIT ?",
                (json.dumps(query_vec), limit),
            )
        return [dict(r) for r in rows]
