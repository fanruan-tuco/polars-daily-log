"""Worklog publisher abstraction — submit worklogs to external platforms.

The ``WorklogPublisher`` protocol defines the contract all publishers
implement. ``PublisherRegistry`` resolves the right publisher for a given
summary type by reading ``summary_types.publisher_name`` from the DB.

Phase 1 ships ``JiraPublisher`` only. Adding a new platform (Feishu,
Notion, Webhook, …) means dropping a new module in this package and
registering it in ``PUBLISHER_FACTORIES``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class PublishResult:
    """Uniform result of a single worklog submission."""
    success: bool
    worklog_id: str = ""             # platform's id for the created entry
    platform: str = ""               # "jira", "feishu", …
    raw: Optional[dict] = None       # full API response (for audit logging)
    error: str = ""                  # non-empty when success=False


@runtime_checkable
class WorklogPublisher(Protocol):
    """Contract for any platform that accepts worklog submissions.

    Implementations live in submodules (``jira.py``, ``feishu.py``, …).
    """

    name: str             # machine key: "jira", "feishu"
    display_name: str     # human label: "Jira", "飞书"

    async def submit(
        self,
        *,
        issue_key: str,
        time_spent_sec: int,
        comment: str,
        started: str,
    ) -> PublishResult:
        """Push a single worklog entry. Must not raise — errors go in
        ``PublishResult.error``."""
        ...

    async def delete(self, worklog_id: str, *, issue_key: str) -> bool:
        """Remove a previously submitted worklog. Best-effort."""
        ...

    async def check_connection(self) -> bool:
        """Quick health check (e.g. ``GET /myself``). Returns False on any error."""
        ...
