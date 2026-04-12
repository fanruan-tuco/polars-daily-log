DEFAULT_SUMMARIZE_PROMPT = """你是工作日志助手。以下是用户今天的工作数据：

【日期】{date}

【活跃 Jira 任务】
{jira_issues}

【Git Commits】
{git_commits}

【活动记录】
{activities}

请根据以上数据总结今天的工作内容，生成工作日志。

规则：
- 如果有活跃的 Jira 任务，请根据工作内容判断哪些活动属于哪个任务，为每个相关任务生成一条日志，同时将无法归类的内容放入 issue_key 为 "OTHER" 的条目
- 如果没有活跃的 Jira 任务，请将所有内容汇总为一条日志，issue_key 使用 "ALL"
- 每条日志包含工时和具体做了什么（中文，50-150字）
- 工时精确到 0.5h
- 重点描述具体的工作内容，不要只列统计数据

以 JSON 数组格式返回：
[
  {
    "issue_key": "PROJ-101 或 ALL 或 OTHER",
    "time_spent_hours": 3.5,
    "summary": "具体工作内容描述..."
  }
]"""


DEFAULT_AUTO_APPROVE_PROMPT = """你是工作日志审批助手。请检查以下工作日志草稿：

【日期】{date}
【Jira 任务】{issue_key}: {issue_summary}
【工时】{time_spent_hours} 小时
【日志内容】{summary}
【关联 Git Commits】{git_commits}

请判断：
1. 日志内容是否与 Git commits 和任务描述一致？
2. 工时是否合理？
3. 日志描述是否清晰、具体？

如果合格返回 {"approved": true}
如果不合格返回 {"approved": false, "reason": "不通过原因"}"""


DEFAULT_PERIOD_SUMMARY_PROMPT = """你是工作周报/月报助手。以下是用户在 {period_start} ~ {period_end} 期间的每日工作日志：

{daily_logs}

请生成一份{period_type}总结，要求：
1. 按主要工作方向分类汇总（如：功能开发、Bug修复、会议沟通、调研学习等）
2. 每个方向列出具体做了什么，不要泛泛而谈
3. 总结本周期的工作亮点和主要成果
4. 统计总工时
5. 用中文，200-500字

以纯文本格式返回，不需要 JSON。"""


def render_prompt(template: str, **kwargs) -> str:
    """Safe template rendering — uses simple string replacement instead of .format()
    to avoid issues with curly braces in user data (OCR text, commit messages, etc.)."""
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result
