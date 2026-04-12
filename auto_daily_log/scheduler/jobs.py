import json
import re
from datetime import date, datetime
from typing import Optional

from ..config import AutoApproveConfig
from ..models.database import Database
from ..summarizer.engine import LLMEngine
from ..summarizer.prompt import DEFAULT_AUTO_APPROVE_PROMPT, render_prompt


class DailyWorkflow:
    def __init__(self, db: Database, engine: LLMEngine, auto_approve_config: AutoApproveConfig):
        self._db = db
        self._engine = engine
        self._auto_approve_config = auto_approve_config

    async def run_daily_summary(self, target_date: Optional[str] = None) -> list[dict]:
        from ..collector.git_collector import GitCollector
        from ..summarizer.summarizer import WorklogSummarizer

        target = target_date or date.today().isoformat()
        collector = GitCollector(self._db)
        await collector.collect_today()
        summarizer = WorklogSummarizer(self._db, self._engine)
        drafts = await summarizer.generate_drafts(target)
        return drafts

    async def auto_approve_pending(self, target_date: str) -> None:
        if not self._auto_approve_config.enabled:
            return

        drafts = await self._db.fetch_all(
            "SELECT * FROM worklog_drafts WHERE date = ? AND status = 'pending_review'",
            (target_date,),
        )

        prompt_template = await self._get_auto_approve_prompt()

        for draft in drafts:
            issue = await self._db.fetch_one(
                "SELECT * FROM jira_issues WHERE issue_key = ?", (draft["issue_key"],),
            )

            commits = await self._db.fetch_all(
                "SELECT * FROM git_commits WHERE date = ?", (target_date,)
            )
            commits_text = "\n".join(f"- {c['message']}" for c in commits) or "无"

            prompt = render_prompt(
                prompt_template,
                date=target_date,
                issue_key=draft["issue_key"],
                issue_summary=issue["summary"] if issue else "",
                time_spent_hours=round(draft["time_spent_sec"] / 3600, 1),
                summary=draft["summary"],
                git_commits=commits_text,
            )

            raw_response = await self._engine.generate(prompt)
            result = self._parse_approval(raw_response)

            if result.get("approved"):
                await self._db.execute(
                    "UPDATE worklog_drafts SET status = 'auto_approved', updated_at = datetime('now') WHERE id = ?",
                    (draft["id"],),
                )
                await self._db.execute(
                    "INSERT INTO audit_logs (draft_id, action, after_snapshot) VALUES (?, 'auto_approved', ?)",
                    (draft["id"], raw_response),
                )
            else:
                await self._db.execute(
                    "INSERT INTO audit_logs (draft_id, action, after_snapshot) VALUES (?, 'auto_rejected', ?)",
                    (draft["id"], raw_response),
                )

    def _parse_approval(self, response: str) -> dict:
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {"approved": False, "reason": "Failed to parse LLM response"}

    async def _get_auto_approve_prompt(self) -> str:
        setting = await self._db.fetch_one(
            "SELECT value FROM settings WHERE key = 'auto_approve_prompt'"
        )
        if setting:
            return setting["value"]
        return DEFAULT_AUTO_APPROVE_PROMPT
