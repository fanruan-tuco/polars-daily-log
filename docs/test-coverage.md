# 测试覆盖矩阵

> 本文面向参与本项目的 AI 助手和开发者。新增功能必须满足对应层级的测试要求。

---

## 测试层级

```
┌─────────────────────────────────────────────────┐
│  Layer 4: Real Install (test_install_real.py)    │  真 wheel、真 pip、隔离 HOME
│  — 从零安装 / 升级安装 / 数据迁移              │  @pytest.mark.slow
├─────────────────────────────────────────────────┤
│  Layer 3: E2E Lifecycle (test_e2e_full_lifecycle)│  12 阶段全链路、mock LLM+Jira
│  — 空环境→采集→生成→审批→提交→删除            │
├─────────────────────────────────────────────────┤
│  Layer 2: Integration (test_api_*, test_scope_*) │  真 DB、真 FastAPI、mock 外部
│  — API 行为、scheduler 逻辑、config 解析        │
├─────────────────────────────────────────────────┤
│  Layer 1: Unit (test_classifier, test_config...) │  纯函数、无 IO
│  — 分类器、URL 解析、4-byte scrub               │
└─────────────────────────────────────────────────┘
```

---

## 场景覆盖清单

### 安装脚本 (install.sh / install.ps1)

| 场景 | 测试文件 | 用例数 | 平台 |
|------|---------|--------|------|
| role=server/collector/both 分支 | test_install_sh.py | 5 | macOS/Linux |
| 无 tty 默认 both | test_install_sh.py | 1 | macOS/Linux |
| 非法 role 退出 | test_install_sh.py | 1 | macOS/Linux |
| VERSION 动态读取 | test_install_sh.py | 1 | macOS/Linux |
| config.yaml 创建/跳过 | test_install_sh.py | 4 | macOS/Linux |
| collector.yaml 创建/跳过/特殊字符 | test_install_sh.py | 4 | macOS/Linux |
| both 模式不因 collector.yaml 存在跳过 server | test_install_sh.py | 1 | macOS/Linux |
| builtin LLM: 正确/错误/空口令/无 enc/collector 跳过 | test_install_sh.py | 5 | macOS/Linux |
| 节号无重复 | test_install_sh.py | 1 | macOS/Linux |
| 前端 release 跳过/collector 跳过 | test_install_sh.py | 2 | macOS/Linux |
| 自动启动 | test_install_sh.py | 1 | macOS/Linux |
| pip 镜像默认/自定义 | test_install_sh.py | 2 | macOS/Linux |
| 数据目录创建 | test_install_sh.py | 1 | macOS/Linux |
| dev/release/unknown 模式 | test_install_sh.py | 2 | macOS/Linux |
| **Windows 对应场景** | test_install_ps1.py | 15 | Windows |

### 真实安装 (真 wheel, 不 mock)

| 场景 | 测试文件 | 用例数 |
|------|---------|--------|
| **从零安装 server**: venv + wheel + config + builtin + import + DB | test_install_real.py | 1 |
| **从零安装 both**: 两个 config 都生成 | test_install_real.py | 1 |
| **从零安装 collector**: 不建 server config, 不解密 LLM | test_install_real.py | 1 |
| **升级保留 settings** (LLM key, trigger time, nickname) | test_install_real.py | 1 |
| **升级保留 activities** | test_install_real.py | 1 |
| **升级保留 worklogs** | test_install_real.py | 1 |
| **升级不覆盖 config.yaml** | test_install_real.py | 1 |
| **升级不覆盖 builtin.key** | test_install_real.py | 1 |
| **升级后新表可用** | test_install_real.py | 1 |

### Scheduler

| 场景 | 测试文件 | 用例数 |
|------|---------|--------|
| summary_types 表存在时注册 job | test_scheduler_table_compat.py | 1 |
| **无 time_scopes 表时仍能工作** | test_scheduler_table_compat.py | 1 |
| Settings UI 触发时间 override (job 注册) | test_scope_scheduler.py | 2 |
| **Settings UI override (catchup)** | test_scheduler_table_compat.py | 2 |
| packaging 模块可 import | test_scheduler_table_compat.py | 1 |
| updater/version_check 可 import | test_scheduler_table_compat.py | 1 |
| scope 注册/禁用/损坏/weekly/monthly | test_scope_scheduler.py | 6 |
| catchup: 未到时间/已生成/多 scope/部分失败/损坏/无 scope | test_scope_scheduler.py | 8 |

### API

| 场景 | 测试文件 | 用例数 |
|------|---------|--------|
| settings CRUD / jira-status / check-llm | test_api_settings.py | ~8 |
| dashboard extended / machines / timeline / recent | test_api_dashboard_extended.py | ~12 |
| worklogs generate / approve / reject / submit | test_api_worklogs.py | ~6 |
| activities CRUD / timeline / recycle | test_api_timeline.py | ~10 |
| chat session / streaming / retrieval | test_api_chat.py | ~40 |
| E2E 12-phase lifecycle | test_e2e_full_lifecycle.py | 1 (12 phases) |

### 依赖 / Import

| 场景 | 测试文件 |
|------|---------|
| `packaging.version.Version` 可用 | test_scheduler_table_compat.py |
| `auto_daily_log.updater.version_check` 可 import | test_scheduler_table_compat.py |
| wheel 安装后全模块 import 链 | test_install_real.py (5 个 import 检查) |

---

## 运行指南

```bash
# 常规（CI 默认）— 排除 slow 标记
pytest tests/ -q

# 包含真实安装测试（本地调试 / release 前验证）
pytest tests/ -q -m "slow or not slow" --timeout=300

# 只跑安装相关
pytest tests/test_install_sh.py tests/test_install_real.py -v

# 只跑 scheduler 相关
pytest tests/test_scope_scheduler.py tests/test_scheduler_table_compat.py -v
```

---

## 新增功能的测试要求

**以下是硬性要求，PR 合并前必须满足：**

1. **新增 Python 依赖** → `test_scheduler_table_compat.py` 或同类文件加一条 import 断言
2. **修改 install.sh / install.ps1** → `test_install_sh.py` / `test_install_ps1.py` 加对应分支用例
3. **修改 DB schema** → `test_install_real.py` 的升级测试验证旧数据存活
4. **新增 API endpoint** → `test_e2e_full_lifecycle.py` 的 regression gate 加一行
5. **修改 scheduler 逻辑** → `test_scope_scheduler.py` + `test_scheduler_table_compat.py`
6. **修改 settings 页面** → 至少手动验证 dirty tracking（前端暂无自动化）
7. **所有断言必须精确**：`assert x == 'expected'`，严禁 `assert x` / `assert len(x) > 0`
