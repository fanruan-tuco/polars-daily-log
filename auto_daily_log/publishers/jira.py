"""JiraPublisher — wraps the existing JiraClient behind the WorklogPublisher protocol."""
from __future__ import annotations

from ..jira_client.client import JiraClient
from . import PublishResult


class JiraPublisher:
    """Adapts ``JiraClient`` to the ``WorklogPublisher`` protocol.

    Construction is cheap — the heavy work (HTTP) happens inside
    ``submit`` / ``delete`` / ``check_connection``.
    """

    name = "jira"
    display_name = "Jira"

    def __init__(self, client: JiraClient) -> None:
        self._client = client

    async def submit(
        self,
        *,
        issue_key: str,
        time_spent_sec: int,
        comment: str,
        started: str,
    ) -> PublishResult:
        try:
            raw = await self._client.submit_worklog(
                issue_key=issue_key,
                time_spent_sec=time_spent_sec,
                comment=comment,
                started=started,
            )
            return PublishResult(
                success=True,
                worklog_id=str(raw.get("id", "")),
                platform=self.name,
                raw=raw,
            )
        except Exception as exc:
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def delete(self, worklog_id: str, *, issue_key: str) -> bool:
        # Jira REST: DELETE /rest/api/2/issue/{key}/worklog/{id}
        try:
            import httpx
            url = self._client._url(f"/rest/api/2/issue/{issue_key}/worklog/{worklog_id}")
            async with httpx.AsyncClient(timeout=15.0, trust_env=False) as http:
                r = await http.delete(url, headers=self._client._headers())
                return r.status_code < 400
        except Exception:
            return False

    async def check_connection(self) -> bool:
        return await self._client.test_connection()
