# 内置 LLM 配置（口令解密）

> 让朋友/同事拿到 tarball 后，不用自己注册 LLM key 就能一键用起来。
> 作者（Conner）本地保有一个共享的 Kimi API key，口头把解密口令告诉信任圈内的用户。
> 这是**个人工具**的共享场景，不是公开分发——所有设计都围绕这个前提。

---

## 威胁模型（先看这个）

这套机制**只防自动扫描器**，**不防人肉**。

| 防得住 | 防不住 |
|--------|--------|
| GitHub / GitLeaks 的 `sk-...` 正则扫描 | 任何 `git clone` 后读 `install.sh` 的人 |
| Moonshot 自家 secret 扫描器（自动吊销 key） | 会 `openssl` 的人 |
| 顺手 grep 仓库的 drive-by 抓取 | 恶意分析师 |

密文用标准 `openssl aes-256-cbc -pbkdf2` 生成，扫描器看到的就是一串 base64，不会触发任何 `sk-...` 模式匹配。**口令本身在源码里是硬编码的** (`polars`)——这不是 bug，是特意的：我们只需要把密文"漂白"成不像 API key 的样子，不需要真防解密。

一旦有朋友把口令外传出去并遭滥用，解决办法就三步：
1. Moonshot 后台 revoke 老 key
2. 改 `.secrets/builtin.json` 填新 key（可顺便换口令）
3. 重跑 `bash scripts/encrypt-builtin.sh` → commit → 发新 release

---

## 组件

```
.secrets/builtin.json          明文（.gitignored，只在作者本地）
  └─ encrypt-builtin.sh (口令=polars) →
       auto_daily_log/builtin_llm.enc    密文 blob（入库，安全）
         └─ release.sh 打进 tarball →
              install.sh (prompt 口令) →
                ~/.auto_daily_log/builtin.key (0600)
                  └─ builtin_llm.py.load_builtin_llm_config() →
                       worklogs._get_llm_engine_from_settings() fallback
                       search._get_searcher() fallback
```

---

## 作者工作流

### 首次设置

```bash
cp .secrets/builtin.json.example .secrets/builtin.json
# 编辑 .secrets/builtin.json，填入真实的 engine / api_key / base_url / model
bash scripts/encrypt-builtin.sh
git add auto_daily_log/builtin_llm.enc
git commit -m "chore: refresh built-in LLM blob"
```

### 轮换 key

同上。`encrypt-builtin.sh` 会直接覆盖 `builtin_llm.enc`。

### 修改解密口令

改 `scripts/encrypt-builtin.sh` 里的 `PASSPHRASE`，重新加密，commit。
**注意**：老口令的 release 用户还能解老版 blob，直到他们升级。

---

## 用户安装流程

```
$ curl -fsSL https://.../bootstrap.sh | bash
...
7. Built-in LLM (optional)
  如果作者告诉你口令，输入可自动配置 LLM；直接回车跳过。
  口令: polars
  ✓ 内置 LLM 已配置 → /Users/me/.auto_daily_log/builtin.key
...
```

三种输入情况：
- **正确口令** → 解密 + 写入 `~/.auto_daily_log/builtin.key`（0600）
- **回车/空** → 跳过。用户之后去 Settings 页自己配 LLM
- **错误口令** → openssl 非零退出，打印警告，继续安装（不 block）

非交互安装（CI / scripted）走环境变量：
```bash
PDL_BUILTIN_PASSPHRASE=polars bash install.sh
```

---

## 运行时解析优先级

`auto_daily_log/builtin_llm.py::load_builtin_llm_config()` 依次检查：

1. `~/.auto_daily_log/builtin.key` — install.sh 写的正式路径
2. `REPO_ROOT/.secrets/builtin.json` — **dev 便利**，从源码跑 `./pdl start` 时不用先走装机流程

调用侧的完整 fallback 链（`worklogs._get_llm_engine_from_settings`）：

```
settings 表 llm_api_key  →  builtin.key  →  返回 None（调用者降级）
```

用户在 Settings 页手动填的 key **始终优先于** builtin。这点很关键：用户可能对默认模型不满意想自己配——不能被我们的 builtin 覆盖掉。

---

## 数据格式

`.secrets/builtin.json` / `~/.auto_daily_log/builtin.key` 结构：

```json
{
  "engine": "openai_compat",
  "api_key": "sk-...",
  "base_url": "https://api.kimi.com/coding",
  "model": "kimi-k2"
}
```

- `engine`: `openai_compat` / `anthropic` / `ollama`（与 Settings 页同集合）
- 其它字段语义和 Settings 页一致

---

## 常见维护操作

**查看当前打包的密文**：`cat auto_daily_log/builtin_llm.enc | head -2`（只会看到 base64，读不出原文）

**解密验证**：
```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -base64 \
    -in auto_daily_log/builtin_llm.enc -pass pass:polars
```

**清掉本机已解密的 key**：`rm ~/.auto_daily_log/builtin.key`（下次用户触发 LLM 调用就会 fallback 到 None）

**验证用户没装 builtin 时的降级**：临时 `mv ~/.auto_daily_log/builtin.key{,.bak}`，触发日报生成，应看到"请配置 LLM"相关提示而不是崩溃。
