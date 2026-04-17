"""API for summary type configuration (Phase 1: read-only)."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["summary-types"])


@router.get("/summary-types")
async def list_summary_types(request: Request):
    """Return all summary types, built-in first."""
    db = request.app.state.db
    rows = await db.fetch_all(
        "SELECT * FROM summary_types ORDER BY is_builtin DESC, name"
    )
    return [dict(r) for r in rows]
