"""Publisher registry — resolve the right publisher for a summary type.

Call ``get_publisher(db, summary_type_name)`` → ``WorklogPublisher | None``.
Returns None when the summary type has no publisher configured (e.g. weekly
reports that don't get pushed anywhere).
"""
from __future__ import annotations

from typing import Optional

from ..models.database import Database
from . import WorklogPublisher


async def get_publisher(db: Database, summary_type_name: str) -> Optional[WorklogPublisher]:
    """Build and return the publisher configured for ``summary_type_name``.

    Each call creates a fresh publisher instance (cheap) because the
    underlying credentials may change between calls (user re-logins).
    """
    row = await db.fetch_one(
        "SELECT publisher_name FROM summary_types WHERE name = ?",
        (summary_type_name,),
    )
    if not row or not row.get("publisher_name"):
        return None

    name = row["publisher_name"]
    factory = _FACTORIES.get(name)
    if factory is None:
        return None
    return await factory(db)


async def _build_jira(db: Database) -> WorklogPublisher:
    from ..jira_client.client import build_jira_client_from_db
    from .jira import JiraPublisher
    client = await build_jira_client_from_db(db)
    return JiraPublisher(client)


# ── Factory map — add new publishers here ──────────────────────────────
_FACTORIES: dict = {
    "jira": _build_jira,
    # "feishu": _build_feishu,   # Phase 2
    # "webhook": _build_webhook, # Phase 2
}
