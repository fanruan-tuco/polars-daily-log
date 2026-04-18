# CoDaily / 日报广场（polars-daily-plaza）— 设计

- **Date:** 2026-04-19
- **Status:** Design approved; ready for implementation planning
- **Repo to create:** `polars-daily-plaza`（新 repo，独立于 PDL）
- **Product brand:** CoDaily（英文）/ 日报广场（中文）
- **Contract version:** push-contract v1.0

---

## 1. 背景与问题

PDL（Polars Daily Log）是一个**本地个人日报工具**：采集活动、生成总结、推 Jira。设计原则明确写在 `AGENTS.md` 里 —— "个人工具，数据只在自己机器上，不跨用户共享"。

但真实工作中存在**日报交换**的诉求：作为项目负责人，想知道协作者今天做了什么；作为协作者，想把工作进展同步给相关方。直接把 PDL 扩成多用户 SaaS 会**与本地工具定位冲突**。

**CoDaily 解决这个缺口：一个独立于 PDL 的中转 + 展示平台**。PDL 只需新增一个 publisher 把日报推到 CoDaily，其它一切（账户、订阅、feed）在 CoDaily 自己完成。两个项目零代码耦合，只通过 HTTP 契约通信。

### MVP 范围

- **用户形态：** 闭环小组（邀请制），首批 2~5 个 fanruan 同事
- **部署形态：** 单一 fanruan Jira 实例作 IDP；单一 CoDaily 实例
- **核心能力：** 单向关注、被订阅者可见 followers、feed 展示

### 非目标（明确 Out-of-Scope）

- 公开 SaaS 注册 / 付费 / 多公司多 Jira 租户
- 多群组 / 分组权限
- 实时推送 / 通知
- 手动发帖编辑器（CoDaily 被动接收 publisher，不做内容创作 UI）
- 搜索 / 全文索引 / embedding
- 移动 app / 桌面 app

---

## 2. 架构总览

### 三个独立部件

```
┌──────────────┐         HTTP push            ┌───────────────────┐
│  PDL (用户A)  │ ────────────────────────► │                   │
│ + CoDaily-   │                                │                   │
│  Publisher   │      ◄── GET /feed ──────     │  CoDaily 后端     │
└──────────────┘                                │  (FastAPI+SQLite) │
                                                │                   │
┌──────────────┐         HTTP push              │  + 前端静态文件    │
│  PDL (用户B)  │ ────────────────────────► │  (Vue 3 dist)     │
└──────────────┘                                └────────┬──────────┘
                                                         │
                    浏览器访问 codaily.fanruan.com       │
                         ┌──────────────────┐           │
                         │  任意被邀请用户    │ ◄─────────┘
                         │  (Jira 账号登录)   │
                         └──────────────────┘
```

| 部件 | 技术栈 | 职责 | 仓库 |
|------|-------|-----|------|
| CoDaily 后端 | FastAPI + SQLite(WAL) | auth、CRUD、API、静态文件托管 | 新建 `polars-daily-plaza` |
| CoDaily 前端 | Vue 3 + Element Plus + Vite | 登录/Feed/档案/设置/管理员页 | 同 repo `web/frontend/` |
| CoDaily Publisher | Python，PDL 的 `WorklogPublisher` 协议 | 把 PDL scope_output 内容 POST 到 CoDaily | **PDL 仓库** `auto_daily_log/publishers/codaily.py` |

### 边界纪律

- **零代码共享**：两仓库不互相 import；只走 HTTP API
- **Publisher 是唯一触点**：PDL 其它代码不知道 CoDaily 存在
- **客户端类型无感**：`POST /api/v1/push` 欢迎任何客户端，不绑 PDL

### 技术栈选择理由

方案 1 胜出（Python/FastAPI + Vue/Element Plus），理由：
- 作者已熟练此栈（PDL 就是此栈跑起来的），最快 ship
- 和 PDL UI 风格自然一致（都 Element Plus），但代码独立演进
- VPS + Docker 部署可控，不绑定特定 PaaS
- SQLite + WAL 对 MVP（少量读写）完全够用；迁 PostgreSQL 只需改 SQLAlchemy 配置

---

## 3. 数据模型

### SQLite Schema

```sql
-- ① users: Jira 验证通过 + 在 invites 白名单 → 自动 upsert
CREATE TABLE users (
    jira_username TEXT PRIMARY KEY,      -- Jira 用户名作 PK（稳定、唯一、URL 友好）
    display_name TEXT NOT NULL,
    email TEXT,
    avatar_url TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- ② invites: admin 管理白名单
CREATE TABLE invites (
    jira_username TEXT PRIMARY KEY,
    invited_by TEXT NOT NULL,             -- admin 的 jira_username
    invited_at TEXT DEFAULT (datetime('now')),
    consumed_at TEXT,                      -- 首次登录成功时填
    note TEXT                              -- admin 备注（可选）
);

-- ③ sessions: 浏览器登录 token + PDL publisher 长期 token 共用此表
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,           -- SHA-256(token)，DB 不存明文
    jira_username TEXT NOT NULL,
    client_kind TEXT NOT NULL,             -- 'browser' | 'pdl-publisher'
    created_at TEXT DEFAULT (datetime('now')),
    last_used_at TEXT,
    expires_at TEXT,                       -- browser=30天后；pdl-publisher=NULL（永不过期）
    revoked_at TEXT,
    label TEXT                             -- 用户起的名字，如 "我的 MacBook PDL"
);

-- ④ follows: 单向关注
CREATE TABLE follows (
    follower TEXT NOT NULL,
    followee TEXT NOT NULL,
    followed_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (follower, followee)
);
CREATE INDEX idx_follows_followee ON follows(followee);

-- ⑤ posts: 日报（格式中立）
CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    post_date TEXT NOT NULL,               -- 日志**描述的日期**（可后补）
    scope TEXT NOT NULL DEFAULT 'day',     -- 任意字符串，PDL 推啥就存啥
    content TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'markdown',
    metadata TEXT DEFAULT '{}',            -- JSON，含 schema_version
    source TEXT,                           -- 'pdl' | 'manual' | ...
    pushed_at TEXT DEFAULT (datetime('now')),  -- 服务器**接收时间**
    updated_at TEXT,                       -- 重推覆盖时更新
    deleted_at TEXT,                       -- 作者软删（回收站）
    UNIQUE(author, post_date, scope)
);
CREATE INDEX idx_posts_author_date ON posts(author, post_date DESC);

-- ⑥ post_hides: follower 从自己 feed 隐藏某条
CREATE TABLE post_hides (
    follower TEXT NOT NULL,
    post_id INTEGER NOT NULL,
    hidden_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (follower, post_id)
);

-- ⑦ audit_log: 谁-什么时候-做了啥
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,                  -- 'login'|'logout'|'push'|'follow'|'unfollow'
                                            -- |'invite'|'revoke-session'|'delete-post'
                                            -- |'restore-post'|'hide-post'
    target TEXT,                           -- 对象（如 followee 的 username、post id）
    detail TEXT,                           -- JSON 额外细节
    ip TEXT,
    user_agent TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_actor ON audit_log(actor, created_at DESC);
```

### 关键设计决定

| 决定 | Why |
|------|-----|
| PK 用 `jira_username` 而非 int ID | Jira 用户名稳定唯一；URL 直接用 `@connery` 有语义 |
| `invites` 白名单独立一张表 | 配合"闭环小组"；admin 手动加人；首次登录 consumed 时机清晰 |
| `sessions` 存 `token_hash` 不存明文 | DB 泄露也无法还原 token，SHA-256 即可 |
| 浏览器 session / PDL token 同表 | `client_kind` 区分；Settings 页统一管理 |
| `posts` UPSERT `UNIQUE(author, post_date, scope)` | 重推覆盖，不保留历史修订版 |
| `content` 格式中立 + `metadata` JSON | 协议是**数据描述**，不是限制；未知字段原样存 |
| 作者软删 `deleted_at` vs follower hide 独立表 | 两种不同语义：作者的"回收站" vs follower 的"从我的视野移除" |
| 不做 `groups` 表 | 整个 invites 白名单就是隐式大组；MVP 不需要 |
| `post_date` vs `pushed_at` 显式分离 | 后补日报场景下必须能区分"日志描述的日期" vs "服务器接收时间" |

---

## 4. Push API 契约（v1.0）

### Endpoint

```
POST /api/v1/push
Authorization: Bearer <pdl-publisher-token>
Content-Type: application/json
```

### Request Body

```json
{
  "post_date": "2026-04-19",
  "scope": "day",
  "content": "# 今日工作\n...",
  "content_type": "markdown",
  "metadata": {
    "schema_version": "1.0",
    "issue_keys": ["POLARDB-123"],
    "time_spent_sec": 12600,
    "entries": [
      {"issue_key": "POLARDB-123", "hours": 2.0, "summary": "修 SQL parser"},
      {"issue_key": "POLARDB-456", "hours": 1.5, "summary": "review 老王 PR"}
    ],
    "tags": ["backend"]
  },
  "source": "pdl"
}
```

### Response

- `201 Created` `{"id": 42, "status": "created"}` — 首次创建
- `200 OK` `{"id": 42, "status": "updated"}` — 已存在，upsert 覆盖
- `400 Bad Request` `{"detail": "metadata present but schema_version missing"}`
- `401 Unauthorized` — token 无效或已吊销
- `403 Forbidden` — token 属于 client_kind != 'pdl-publisher'（阻止浏览器 session 误推）
- `429 Too Many Requests` — 限流命中

### 字段规约

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|-----|
| `post_date` | string(YYYY-MM-DD) | ✅ | 日志描述的日期 |
| `scope` | string | ✅ | 任意字符串（PDL 推啥就是啥） |
| `content` | string | ✅ | 主体内容 |
| `content_type` | string | ❌ | 默认 `markdown`，支持 `markdown`\|`json`\|`text` |
| `metadata` | object | ❌ | 推了则必含 `schema_version` |
| `source` | string | ❌ | 客户端自报家门 |

### Metadata v1.0 规约

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|-----|
| `schema_version` | string | ✅（如推 metadata）| 固定 `"1.0"` |
| `issue_keys` | string[] | ❌ | Jira issue 列表 |
| `time_spent_sec` | int | ❌ | 总工时（秒） |
| `entries` | object[] | ❌ | 每项 `{issue_key, hours, summary}` |
| `tags` | string[] | ❌ | 自由 tag |

**未知字段（非规约内）：** 原样存入 `metadata` JSON；dashboard 忽略。

### 版本兼容规则

| 情况 | CoDaily 行为 |
|------|-------------|
| metadata 缺失 | ✅ 接受；dashboard 只展示 content + 日期 |
| `schema_version = "1.0"` | ✅ 解析所有规约字段 |
| `schema_version = "1.x"`（MINOR 升级）| ✅ 解析已知字段，未知字段原样存 |
| `schema_version = "2.x"` 且 CoDaily 支持 | ✅ 按 2.x 解析 |
| `schema_version = "2.x"` 且 CoDaily 不支持 | ⚠️ 存入 DB，dashboard 退化提示"请升级 CoDaily" |
| `schema_version` 非法或缺失但 metadata 非空 | ❌ 返回 400 |

### 版本升级 SemVer 规则

- **MINOR（1.0 → 1.1）：新增 optional 字段** — 旧 CoDaily 自动忽略新字段，兼容
- **MAJOR（1.x → 2.0）：重命名/删除/语义反转字段** — 旧 CoDaily 退化展示

### 契约文档

放 CoDaily repo `docs/push-contract-v1.md`，每次升级保留历史版本文件。PDL publisher 作者**只读这份 doc**，不读 CoDaily 代码。

---

## 5. Auth 流程（Jira 作 IDP）

### 登录（浏览器）

```
用户访问 codaily.fanruan.com
    ↓
登录页输入 Jira username + password
    ↓
POST /api/v1/auth/login
    ↓
后端调 Jira: GET https://jira.fanruan.com/rest/api/2/myself
              Authorization: Basic base64(username:password)
    ↓                       ↓
  200 OK              401/403
    ↓                       ↓
查 invites 白名单       返回 401 "Jira 验证失败"
    ↓         ↓
白名单里有  白名单里没有
    ↓         ↓
users.upsert() (从 Jira response 取 display_name/email/avatar)
sessions.insert(token_hash, client_kind='browser', expires_at=now+30d)
    ↓                       返回 403 "未被邀请，请联系管理员"
Set-Cookie: codaily_session=<明文token>; HttpOnly; Secure; SameSite=Strict; Path=/
返回 200 + user info
```

### PDL publisher 拿长期 token

```
用户浏览器已登录 → Settings → Sessions tab → "Generate PDL Token"
填写 label（如 "MacBook PDL"）
    ↓
POST /api/v1/sessions/pdl-token
sessions.insert(token_hash, client_kind='pdl-publisher', expires_at=NULL)
    ↓
前端**一次性明文**显示：`cd_pdl_abc123...xyz`
提示："此 token 只显示一次，请立即复制到 PDL Settings"
    ↓
用户粘贴到 PDL Settings → scope_output publisher_config = {"url": "...", "token": "..."}
```

### 退出 / 吊销

- 退出：`POST /api/v1/auth/logout` → `sessions.revoked_at=now()`
- Settings 页 "Sessions" tab 列出所有 session，每条可单独 revoke
- 所有后续带已吊销 token 的请求 → 401

### 安全规约

| 风险 | 缓解 |
|------|-----|
| Jira 密码明文传输 | **强制 HTTPS**（Caddy 自动 Let's Encrypt） |
| DB 泄露 → token 冒用 | `sessions.token_hash` 存 SHA-256 |
| XSS 偷 session cookie | `HttpOnly` + `SameSite=Strict` |
| 暴力破解 Jira 密码 | `/auth/login` 限流：每 IP 10 次/分钟 |
| Token 泄露 | Settings 可立即 revoke |

---

## 6. API endpoints

### Auth
```
POST   /api/v1/auth/login              {username, password} → cookie + user
POST   /api/v1/auth/logout             吊销当前 session
GET    /api/v1/auth/me                 当前用户
GET    /api/v1/sessions                我的所有 session
DELETE /api/v1/sessions/{id}           吊销某 session
POST   /api/v1/sessions/pdl-token      生成 PDL token，{label} → 一次性明文
```

### Posts
```
POST   /api/v1/push                    publisher 用；upsert 见 Section 4
GET    /api/v1/posts?author=&from=&to=&issue_key=   列表
GET    /api/v1/posts/{id}              单条
DELETE /api/v1/posts/{id}              作者软删
POST   /api/v1/posts/{id}/restore      作者从回收站恢复
POST   /api/v1/posts/{id}/hide         follower 从自己 feed 隐藏
POST   /api/v1/posts/{id}/unhide       恢复显示
```

### Follow
```
GET    /api/v1/users                   用户目录（所有注册用户）
GET    /api/v1/users/{username}        档案页用
POST   /api/v1/follows                 {followee}
DELETE /api/v1/follows/{followee}      取关
GET    /api/v1/follows/following       我关注的
GET    /api/v1/follows/followers       关注我的
```

### Feed
```
GET    /api/v1/feed?limit=&cursor=     游标分页；已 hide 和软删的排除
```

### Admin（需 `is_admin=1`）
```
GET    /api/v1/admin/invites
POST   /api/v1/admin/invites           {jira_username, note}
DELETE /api/v1/admin/invites/{username}
GET    /api/v1/admin/audit?actor=&action=&from=&to=&limit=
```

### Health
```
GET    /health                         {status, db, version}
```

---

## 7. 前端页面

| 路由 | 页面 | 核心组件 |
|------|------|---------|
| `/login` | 登录页 | 用户名密码表单；拒绝时提示"需管理员邀请" |
| `/` | Feed 页（默认首页） | 时间线；左 sidebar 关注列表 + 过滤；右主区按 post_date DESC |
| `/u/:jira_username` | 用户档案页 | 头像 + 关注按钮 + 该用户的 post 列表 |
| `/settings` | 个人设置页 | Sessions / 回收站 / Followers 三 tab |
| `/settings/admin` | 管理员页（仅 admin）| Invites / Audit log 二 tab |

### Feed 页布局
- Header: logo + 搜索框 + 头像下拉
- 左 sidebar: 关注列表 + 过滤器（仅今天 / 仅工作日 / 按 issue）
- 主区：时间线，按日期分组，每 post 展示 author / pushed_at / 内容 + 底部 [hide] [跳 Jira] 小按钮（低调位置）
- 默认加载最近 30 天；滚到底加载更早

### UI 约定
- 小按钮（hide / 跳 Jira）放每条 post 右下角，**低调不打扰**
- URL 中的用户名用 `jira_username`（英文稳定）
- 复用 Element Plus 组件，风格与 PDL 一致

---

## 8. PDL Publisher 实现（PDL 侧）

### 新增文件 `auto_daily_log/publishers/codaily.py`

```python
# 代码草图 — 最终实现在 PDL repo 另开 PR
import httpx
from .base import WorklogPublisher

class CoDailyPublisher(WorklogPublisher):
    """Push daily log to CoDaily. Implements push-contract v1.0."""

    def __init__(self, server_url: str, token: str):
        self.server_url = server_url.rstrip("/")
        self.token = token

    async def publish(self, *, author, post_date, scope, content, entries) -> str:
        metadata = {
            "schema_version": "1.0",
            "issue_keys": sorted({e.issue_key for e in entries if e.issue_key}),
            "time_spent_sec": sum(int(e.hours * 3600) for e in entries),
            "entries": [
                {"issue_key": e.issue_key, "hours": e.hours, "summary": e.summary}
                for e in entries
            ],
        }
        resp = await httpx.AsyncClient().post(
            f"{self.server_url}/api/v1/push",
            json={
                "post_date": post_date,
                "scope": scope,
                "content": content,
                "content_type": "markdown",
                "metadata": metadata,
                "source": "pdl",
            },
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return str(resp.json()["id"])
```

### 注册
`auto_daily_log/publishers/registry.py` 加 `_FACTORIES["codaily"] = _build_codaily_publisher`。

### 用户配置流程
1. 浏览器登录 CoDaily → Settings → 生成 PDL token（复制）
2. 回 PDL Settings → 选某个 scope_output → publisher = `codaily`，config = `{"url": "https://codaily.fanruan.com", "token": "..."}`
3. 保存 → 下次 scope 生成自动 push

### PDL 侧错误处理

| 错误 | 处理 |
|------|-----|
| 网络超时 | 指数退避重试 3 次 |
| 401 token 失效 | 记 audit log；不重试；Settings 红点提醒 |
| 400 schema 错 | 记错误；不重试；Settings 错误面板 |
| 5xx 服务器错 | 退避重试 N 次，超后同 401 提醒 |

---

## 9. 部署

### 目标环境
- 单 VPS（$5/月，DigitalOcean / Hetzner / 类似）
- Docker + docker-compose
- Caddy 做反向代理 + 自动 Let's Encrypt HTTPS
- SQLite 存在挂载 volume

### docker-compose.yml

```yaml
services:
  app:
    image: codaily:latest
    environment:
      - CODAILY_DB=/data/codaily.db
      - CODAILY_JIRA_BASE=https://jira.fanruan.com
      - CODAILY_ADMIN=connery
      - CODAILY_LOG_LEVEL=INFO
    volumes:
      - codaily-data:/data
    restart: unless-stopped

  caddy:
    image: caddy:latest
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy-data:/data
    restart: unless-stopped

volumes:
  codaily-data:
  caddy-data:
```

### Caddyfile

```
codaily.fanruan.com {
    reverse_proxy app:8000
}
```

### 首次部署步骤
1. 买 VPS，解析 DNS `codaily.fanruan.com → VPS IP`
2. `docker compose up -d`
3. Caddy 自动签证
4. 首个 admin（`CODAILY_ADMIN` 环境变量指定的 jira_username）自动获得 `is_admin=1`
5. admin 登录，在 Admin 页加邀请

---

## 10. Ops

### 日志
- stdout 结构化 JSON 日志：`{ts, level, actor, action, detail}`
- docker logs 抓取即可
- 不搞文件轮转（容器外面的事）

### 备份
- Cron 每天凌晨：
  ```bash
  sqlite3 /data/codaily.db ".backup /backups/codaily-$(date +%F).db"
  find /backups -name "codaily-*.db" -mtime +30 -delete
  ```
- 可选：rclone 同步 `/backups` 到 S3

### 限流
- `/auth/login`：每 IP 10 次 / 分钟
- 其它 endpoint：每 token 120 次 / 分钟
- 实现用 `slowapi`

### 健康检查
- `GET /health` → `{"status":"ok","db":"ok","version":"0.1.0"}`
- docker healthcheck 每 30 秒
- 可选：UptimeRobot 免费外网监控

### 监控（v2 之后）
- MVP 阶段不上 Grafana/Prometheus
- docker logs + health check 足够诊断 2~5 人用量

---

## 11. 测试策略

按 PDL 现有 pytest 结构（参考 `AGENTS.md` 的**精确断言原则**）：

| 测试文件 | 覆盖场景 |
|---------|---------|
| `tests/test_auth.py` | 登录成功 / Jira 401 / 白名单拦截 / session 过期 / revoke |
| `tests/test_push.py` | 201 创建 / 200 upsert / 400 schema 错 / 401 token / metadata v1.0 / 未知版本存但不解析 |
| `tests/test_follow.py` | 关注 / 取关 / 幂等 / 自我关注拒绝 / followers 可见 |
| `tests/test_feed.py` | 正确过滤（following + 非 hide + 非软删）/ 游标分页 |
| `tests/test_posts.py` | 作者软删/恢复 / follower hide/unhide / 改 metadata 重推 |
| `tests/test_admin.py` | invites CRUD / 非 admin 访问 admin → 403 / audit 查询 |
| `tests/test_e2e.py` | admin 加白名单 → 用户登录 → push → 关注 → feed 看到 |

### 技术栈
- `pytest` + `pytest-asyncio` + `httpx.AsyncClient`
- Jira 验证 mock 用 `respx` / `pytest-httpx`
- 每个测试独立 in-memory SQLite（`:memory:`）避免串扰

### 精确断言范例

```python
# ✅
assert resp.status_code == 201
assert resp.json()["status"] == "created"
assert resp.json()["id"] == 1

# ❌ 禁止
assert resp.ok
assert "status" in resp.json()
```

---

## 12. 项目结构

```
polars-daily-plaza/
├── codaily/                    # Python package
│   ├── __init__.py
│   ├── app.py                  # FastAPI app factory
│   ├── config.py               # 环境变量读取
│   ├── db.py                   # SQLite 连接 + schema init + 迁移
│   ├── auth/
│   │   ├── jira.py             # Jira 验证客户端
│   │   ├── session.py          # session token 管理
│   │   └── routes.py           # /auth/* endpoints
│   ├── api/
│   │   ├── push.py
│   │   ├── posts.py
│   │   ├── follows.py
│   │   ├── feed.py
│   │   └── admin.py
│   ├── models.py               # Pydantic schemas
│   └── audit.py                # log_action() helper
├── web/frontend/               # Vue 3 + Element Plus
│   ├── src/
│   │   ├── views/
│   │   ├── components/
│   │   └── api/
│   └── vite.config.js
├── tests/
├── docker-compose.yml
├── Dockerfile
├── Caddyfile
├── pyproject.toml
├── AGENTS.md                   # 类似 PDL 的项目原则
├── docs/
│   ├── push-contract-v1.md     # 推送协议契约文档
│   └── deployment.md
└── README.md
```

---

## 13. 设计决定摘要（速查）

| 维度 | 决定 |
|------|-----|
| MVP 范围 | 闭环小组，2~5 个 fanruan 同事 |
| 账户 | Jira 作 IDP（单一 fanruan 实例），密码走 Jira 验证 |
| 注册模型 | admin 白名单邀请制（`invites` 表） |
| 关注模型 | 单向关注，followees 可见 followers |
| 内容格式 | 协议**中立**，publisher 决定；CoDaily 忠实存储 |
| 时间语义 | `post_date`（描述日期）vs `pushed_at`（接收时间）独立 |
| 删除语义 | 作者软删（回收站）vs follower hide（仅隐藏自己视野） |
| Audit log | 启用 |
| 前后端 | 同 repo，Vue 3 + Element Plus + FastAPI |
| DB | SQLite + WAL，够 MVP；未来可迁 PG |
| 部署 | Docker + Caddy + 单 VPS |
| 契约版本 | URL 版本 `/api/v1/` + metadata `schema_version` 双轨 |
| 起始版本 | v1.0（两段 MAJOR.MINOR）|
| Batch push | 不做，PDL 侧责任 |
| 手写发帖 | 不做，MVP 只被动接收 |

---

## 14. 开放问题（留给实施 plan 处理，不阻塞设计）

1. **首次 admin 引导：** `CODAILY_ADMIN=connery` 环境变量写死 vs 更灵活的 CLI 初始化命令 — 倾向环境变量，MVP 够用
2. **Avatar 来源：** Jira 的 avatar URL 可能需要鉴权访问 — 设计阶段假设能匿名访问，实现时如果不行则 CoDaily 拉一次存到本地 `/data/avatars/`
3. **前端状态管理：** Pinia vs Vuex vs 不引入 — 倾向 Pinia，MVP 用不了太多
4. **CI：** GitHub Actions 跑测试；镜像推哪（Docker Hub free / GitHub Container Registry）— 实施时决定

这些都是具体实施时的细节，不影响设计骨架。
