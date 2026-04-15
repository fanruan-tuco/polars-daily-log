# Per-Activity LLM 摘要 — 执行 SUMMARY

**状态**：完成
**执行日期**：2026-04-14 / 2026-04-15
**对应计划**：`2026-04-15-per-activity-llm-summary.md`

---

## 1. 完成标志对照（计划 §8）

| 标志 | 状态 | 说明 |
|------|------|------|
| 所有 phase commit 按顺序打好 | ✅ | 9 个 commit，前缀 `feat: per-activity llm summary — phase N — ...` |
| 测试 ≥241 | ✅ | 实际 **255 passed**（基线 233，净增 22） |
| `activities` 表新列 `llm_summary` + `llm_summary_at` + pending index | ✅ | `models/database.py:_migrate`；新增 4 个 schema test |
| `ActivitySummarizer` 类 | ✅ | `auto_daily_log/summarizer/activity_summarizer.py`，12 个单测覆盖 |
| `DEFAULT_ACTIVITY_SUMMARY_PROMPT` | ✅ | `auto_daily_log/summarizer/prompt.py` |
| `/api/settings/default-prompts` 返回 `activity_summary_prompt` | ✅ | `web/api/settings.py:get_default_prompts` |
| `Activities.vue` 新增 "LLM 摘要" 列 | ✅ | 表格列 + timeline 内联 + 预览弹窗 三处都有展示；NULL → "—"，`(failed)` → 灰色斜体 "—（识别失败）" |
| `Settings.vue` 新增"活动内容猜测 Prompt"编辑框 + 恢复默认按钮 | ✅ | 同现有 3 个模板一致的模式，`PROMPT_KEYS` set 也已纳入 |
| `_compress_activities` 优先用 `llm_summary`，fallback OCR | ✅ | 成功时以 `内容:` 前缀拼接（分号分隔，最多 8 条去重），NULL/`(failed)` 时回退到原 `OCR:` 前 100 字 |
| `WorklogSummarizer.generate_drafts` 开头 `await backfill_for_date` | ✅ | 60s 超时，非阻塞异常 |
| 本 SUMMARY 文档 | ✅ | 就是这份 |

## 2. 各 Phase Commit

| Phase | Hash | Message |
|-------|------|---------|
| 1 — schema | `d796c0a` | phase 1 — schema migration |
| 2 — prompt | `51dacf5` | phase 2 — activity summary prompt template |
| 3 — ActivitySummarizer | `4807759` | phase 3 — ActivitySummarizer worker class |
| 4 — Application 接入 | `d6ee4fe` | phase 4 — wire ActivitySummarizer into Application |
| 5 — daily backfill | `98da25a` | phase 5 — daily-generate synchronous backfill |
| 6 — compress | `e676e94` | phase 6 — _compress_activities prefers llm_summary |
| 7 — Activities.vue | `078830a` | phase 7 — Activities.vue LLM summary column |
| 8 — Settings.vue | `100783d` | phase 8 — Settings.vue activity prompt editor |
| 9 — E2E / SUMMARY | (本 commit) | phase 9 — E2E verification SUMMARY |

## 3. 测试变化

| 指标 | 基线 | 完成后 |
|------|------|--------|
| 测试数 | 233 | **255**（+22） |
| 新测试文件 | — | `tests/test_activity_summarizer.py`（12 cases） |
| 扩充文件 | — | `test_phase_a_schema.py` (+3)，`test_api_settings.py` (+1)，`test_summarizer.py` (+6) |

12 个 ActivitySummarizer case（超过计划要求的 8 个）：
1. 处理一条成功并落库 llm_summary + llm_summary_at
2. LLM 异常时写入 `'(failed)'` 哨兵
3. 跳过 `category='idle'`
4. 跳过 `deleted_at IS NOT NULL`
5. 重试 `'(failed)'` 行
6. prev_summaries 严格同 machine_id（跨机污染隔离）
7. prev_summaries 排除 NULL 和 `'(failed)'`
8. `backfill_for_date` 空 DB 立即返回 0
9. `backfill_for_date` 同时处理 NULL 与 failed
10. signals JSON 里的 tab_title / ocr_text / wecom_group 正确注入 prompt
11. LLM 返回纯空白 → 标记 `'(failed)'`
12. engine 解析为 None → `_process_batch` 返回 0（不忙等）

另外 compress 路径新增 4 个 case（llm_summary 优先、NULL 回退 OCR、`(failed)` 回退 OCR、dedup 去重），generate_drafts 新增 2 个 case（backfill 被调用、backfill 崩溃不阻塞 daily）。

## 4. 风险对照（计划 §7）

| 风险 | 缓解 | 现状 |
|------|------|------|
| 冷启动成本（几千行 NULL 慢慢处理） | Activities 页显示 "—" 不报错；daily backfill 60s 超时后走 OCR fallback | ✅ 实现 |
| LLM key 未配置 | `_get_engine` 返回 None，`_process_batch` 返回 0，主循环按 `POLL_INTERVAL_SEC` 休眠不忙等 | ✅ 实现 + 单测覆盖 |
| `'(failed)'` 永远不恢复 | 每轮 worker 扫到 `'(failed)'` 会重试 | ✅ 实现 + 单测覆盖 |
| Prompt 爆炸 | OCR 不截断（遵循用户意图）；`_compress_activities` 去重 + 上限 8 条 summary 避免 prompt 过大 | ✅ 实现 |
| Daily 生成延迟 | 60s backfill 超时，未完成行走 OCR fallback 不阻塞 | ✅ 实现 |
| 活动数据增长 | llm_summary 列每行 ≤200 字，忽略 | ✅ 无需处理 |

## 5. 约束遵守情况（计划 §6）

| 约束 | 状态 |
|------|------|
| 1. Collector 不加任何逻辑 | ✅ 只改 server 侧 + 前端 |
| 2. LLM 调用必须异步 | ✅ worker 是独立 asyncio task，不阻塞 /api/ingest/* |
| 3. 失败行可重试 | ✅ `'(failed)'` 在下一轮 batch 查询命中 |
| 4. 不改 `/api/ingest/*` 签名 | ✅ 未动 ingest 路由 |
| 5. 不改 AGENTS.md / CLAUDE.md | ✅ 未修改 |
| 6. 不升级依赖 | ✅ 未动 pyproject.toml / requirements.txt |
| 7. prev-N 严格同 machine_id | ✅ SQL `WHERE machine_id=?`，单测验证 |
| 8. 每 phase 一个 commit | ✅ 9 个 commit |
| 9. 测试精确值断言 | ✅ 全部用 `==` / 具体字符串匹配 |
| 10. daily backfill 超时非阻塞 | ✅ try/except 包裹，`processed == 0` 立即返回，OCR fallback 兜底 |

## 6. 已做的 Smoke Test（真 DB + Mock LLM）

手动跑了一段 in-memory demo（临时脚本，已删）：塞入 5 条活动（4 条工作 + 1 条 idle，跨 VSCode/VSCode/Chrome/WeCom），mock engine 按顺序返回 4 段摘要，`backfill_for_date` 调用后：

```
Backfilled 4 rows, LLM called 4 times
  [coding]        VSCode: 在 VSCode 编辑 main.py 文件
  [idle]         (idle): None                             ← 正确跳过
  [coding]        VSCode: 继续调试同一个文件，修复索引越界
  [browsing]      Chrome: 浏览 GitHub 查相关 issue
  [communication] WeCom:  在企业微信里讨论这个 bug

=== _compress_activities output ===
- [coding] VSCode (0.2h): main.py | 内容: 在 VSCode 编辑 main.py 文件；继续调试同一个文件，修复索引越界
- [communication] WeCom (0.1h): 研发小组 | 内容: 在企业微信里讨论这个 bug
```

观察点：
- idle 行留 NULL 不触发 LLM ✓
- prev summaries 随调用次数递增注入 prompt（第 4 次 prompt 长度 382，比第 1 次大）✓
- `_compress_activities` 输出用 `内容:` 前缀 + 分号分隔 + 去重 ✓
- 时长 <0.1h 的活动（Chrome 0.033h）被 `hours < 0.1` 过滤掉（原有行为，未改）✓

（按计划 §5.9 不启动 server；真实 ingest→worker 流程 + 前端显示有待用户手动点 `./pdl server restart` 后验证 —— 代码路径已全部打通，数据库迁移幂等，前端 build 成功。）

## 7. 折中决策 / 遗留 TODO

**折中 1（无影响）**：`backfill_for_date` 调用 `_process_batch`，后者**不做日期过滤**（worker 的本职就是处理全体 pending）。这意味着 backfill 当天的同时可能顺带处理到其他日期的 pending 行。这实际上是好事（加快全局收敛），并在计划 §3 架构图里已隐含描述。已在单测 `test_backfill_processes_failed_rows_too` 里接受这个行为。

**折中 2（命名一致性）**：内部循环用 `_running` 标志而非 `asyncio.Event`，因为 `run()` 只在 lifecycle 的 finally 里被 `stop()` + `cancel()` 同时清理，不会产生 race。计划给的代码原样是 `self._running = False`，也保留。

**遗留 TODO（MVP 以外，计划 §9 已列为不做）**：
- OCR 语义哈希缓存（同 (app, title, ocr_hash) N 分钟内复用结果）
- 活动详情的 "重新识别" 按钮
- Worker 处理进度 UI 实时显示（pending 数、当前处理到哪条）
- Prompt A/B 对比工具
- LLM 费用统计

**遗留未验证（按计划 §5.9）**：
- 真实 server 启动下 `/api/ingest/activities → worker → /api/activities` 端到端链路。代码路径已连通但未在运行中的 server 里 verify。
- 用户首次打开 Settings → Prompt 模板 → 看到第 4 个编辑框是否能保存/恢复默认 roundtrip。前端 build 成功 + 与现有 3 个模板完全同构，可以预期工作。

## 8. 文件清单

**新增**：
- `auto_daily_log/summarizer/activity_summarizer.py`
- `tests/test_activity_summarizer.py`
- `docs/plans/2026-04-15-per-activity-llm-summary-SUMMARY.md`（本文件）

**修改**：
- `auto_daily_log/models/database.py` — 迁移新增 2 列 + 1 索引
- `auto_daily_log/summarizer/prompt.py` — `DEFAULT_ACTIVITY_SUMMARY_PROMPT`
- `auto_daily_log/summarizer/summarizer.py` — 构造参数 + backfill + `_compress_activities`
- `auto_daily_log/scheduler/jobs.py` — DailyWorkflow 接受 summarizer
- `auto_daily_log/app.py` — Application 创建 + 启停 worker，暴露 app.state
- `auto_daily_log/web/api/worklogs.py` — 生成路径取 app.state.activity_summarizer
- `auto_daily_log/web/api/settings.py` — `get_default_prompts` 返回 activity_summary_prompt
- `web/frontend/src/views/Activities.vue` — 表格列 + timeline 行 + 预览弹窗
- `web/frontend/src/views/Settings.vue` — 第 4 个 prompt 编辑卡
- `tests/test_phase_a_schema.py` — 新 schema 测试
- `tests/test_api_settings.py` — default-prompts 测试
- `tests/test_summarizer.py` — compress + backfill 测试
