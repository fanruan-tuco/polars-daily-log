# Windows Install 验证清单（给 AI 协作者的交接单）

> 这份文档是给一个跑在 Windows 机器上的 AI 助手看的。作者（一个 macOS 上的 AI）写完了 `install.ps1`，但**无法在 Windows 上实跑验证**。请按这份清单把剩下的"环境 + 编译"闭环跑通，把发现的问题修进 `install.ps1` + 反馈一份 summary。

**目标（唯一标准）**：在一台干净的 Windows 10/11 机器上，执行下面任一命令，**最后的 Verification 阶段全部打 `OK`**。

```powershell
# 全栈
powershell -ExecutionPolicy Bypass -File install.ps1 -Mode both -SkipScheduledTask

# 只 collector
powershell -ExecutionPolicy Bypass -File install.ps1 -Mode collector -SkipScheduledTask

# 只 server
powershell -ExecutionPolicy Bypass -File install.ps1 -Mode server -SkipScheduledTask
```

---

## 1. 预检查（跑脚本前先确认）

在 PowerShell 里分别执行：

```powershell
$PSVersionTable.PSVersion        # 预期 ≥ 5.1；PS 7 也可
[System.Text.Encoding]::Default  # 看控制台默认编码；cp936/UTF-8 都要兼容
Get-Command git, python, node    # 三个都要在 PATH 里，server 模式需要 node
```

**如果是 PS 7**：`pwsh.exe` 是入口，建议跑：
```powershell
pwsh -ExecutionPolicy Bypass -File install.ps1 -Mode collector -SkipScheduledTask
```

**如果报 `Execution of scripts is disabled on this system`**：当前 session 放开：
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

---

## 2. 必须验证的 5 个点

作者在 macOS 上写的，以下 5 个地方 **没法远程验证**，请你逐一跑一遍。

### 2.1 PowerShell 版本差异（5.1 vs 7）

作者已经**主动避开**了 PS 7-only 的语法：没有 `??`、`?:`、三元操作符、`ForEach-Object -Parallel`。但请实测：

- 跑一次 `-Mode collector -SkipScheduledTask` 在 **PS 5.1**
- 再跑一次在 **PS 7**

**预期**：两边都能过 `Invoke-Verify` 阶段。

**如果 5.1 报 parse error**：大概率是某处用了 PS 7 语法。grep 一下脚本里是否有 `??`、`?.`、`??=`。修成 `if ($x -eq $null) {$default} else {$x}` 这种老写法。

---

### 2.2 `New-ScheduledTask*` cmdlet 行为

作者用了：
```powershell
New-ScheduledTaskAction  ...
New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -Force
```

这些都在 `ScheduledTasks` 模块里（Windows 10+ 自带）。可能问题：

| 症状 | 原因 | 修法 |
|------|------|------|
| `New-ScheduledTaskAction : The term ...` | 当前用户没 ScheduledTasks 模块 | 老机器、WinPE 镜像、精简版 Win 上会缺，要改用 `schtasks.exe` fallback |
| `Access is denied` on Register-ScheduledTask | 任务注册到全局 scope 要管理员 | 把 `-User $env:USERNAME` 换成纯当前用户任务；或检测是否 elevated |
| 域账户 `-User DOMAIN\user` 失败 | 用户名格式 | 用 `$env:USERDOMAIN\$env:USERNAME` |
| `-AtLogOn` 触发器在某些 SKU 上只能系统任务 | Home 版限制 | 降级：创建带登录凭据的任务 |

**测试方法**：去掉 `-SkipScheduledTask` 跑一次，看 step 7 是否 `OK Registered task: ...`。失败时把报错原文反馈。

**兜底策略**：如果 `Register-ScheduledTask` 在目标机器上不可靠，改写成 `schtasks.exe /create /tn "AutoDailyLogServer" /tr "..." /sc ONLOGON /ru "%USERNAME%" /F`（schtasks 更古老但更兼容）。

---

### 2.3 `winocr` 是否能装

`pyproject.toml` 把 `winocr>=0.1.0` 列为 Windows optional dep。实际安装可能要：

- **VC++ Redistributable** 已装
- Windows Runtime APIs 可用（Win10 1903+ / Win11 都可）
- `pywinrt` 底层

**测试**：跑完 install.ps1 后：
```powershell
.\.venv\Scripts\python.exe -c "import winocr; print('OK')"
```

- 成功 → Verification 会打 `OK winocr (Windows native OCR)`
- 失败 → 脚本只 warn 不退出，OCR 功能会禁用，其他都能跑

**如果想把失败变明确**：在 install.ps1 的 `Invoke-Verify` 里把 winocr 从 warn 升级成 fail（但作者建议不要，因为 OCR 本来就是 optional）。

---

### 2.4 `WindowsAdapter` 实际能不能抓窗口

脚本末尾会跑一个 smoke test：

```powershell
.\.venv\Scripts\python.exe -c "from auto_daily_log_collector.platforms.windows import WindowsAdapter; a=WindowsAdapter(); print(a.get_frontmost_app() or '<no foreground>')"
```

**预期输出**：当前前台程序的 ProcessName，例如 `chrome`、`Code`、`explorer`。

**如果输出 `<no foreground>` 或空**：底层 `auto_daily_log/monitor/platforms/windows.py` 靠 PowerShell 里 `user32.dll` 的 `GetForegroundWindow()`。可能问题：

1. `powershell.exe` 在 PATH 里找不到（用 PS 7 环境但 `powershell` 没了）
   - 改成 `pwsh` 或 `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` 完整路径
2. `Add-Type -MemberDefinition` 编译超时（10 秒）
   - 把 `timeout=10` 提高到 30
3. 无窗口进程（比如跑在 Session 0 / SYSTEM 账户）
   - 正常行为，但 smoke test 只取当前 session 的桌面，应该能看到

**如果这项失败**：在 Jira 里开一个 task，说明哪一步失败（不要为了过 smoke test 而削弱 WindowsAdapter，先找到真实根因）。

---

### 2.5 控制台编码 / 中文显示

`install.ps1` 里有少量中文（配置向导 prompt）。默认中文 Windows 是 **cp936** 控制台。

**测试**：跑 `-Mode collector`，到 step 6 配置向导时：

```
  Server URL for this collector [http://127.0.0.1:8888]:
  Collector display name [DESKTOP-XXX]:
```

- 如果显示乱码 → 控制台是 cp936 但脚本被存成了 UTF-8 without BOM
- 修法：把 install.ps1 另存为 **UTF-8 with BOM**（PowerShell 5.1 的潜规则：带 BOM 才能正确识别 UTF-8）

**作者当前保存状态**：UTF-8 without BOM（macOS 默认）。高概率需要你转码。

PowerShell 命令转码：
```powershell
$content = Get-Content -Raw -Encoding UTF8 install.ps1
[System.IO.File]::WriteAllText("$PWD\install.ps1", $content, (New-Object System.Text.UTF8Encoding $true))
```

---

## 3. 验证流程建议

1. **最小路径先跑通**：`-Mode collector -SkipScheduledTask`（最少依赖、不装前端、不注册任务）
2. **扩到 server**：`-Mode server -SkipScheduledTask`（需要 Node.js 18+）
3. **全栈**：`-Mode both -SkipScheduledTask`
4. **打开 scheduled task**：去掉 `-SkipScheduledTask` 跑，验证 step 7
5. **冷启动验证**：重启 Windows，看 Task Scheduler 里任务是否 "Ready" 并在登录后自动拉起

每一步失败就停下来记录，先别进下一步。

---

## 4. 反馈格式

跑完后在 Jira PLS-4626（这个项目的反馈 issue）或者 PR comment 里贴：

```
## 环境
- Windows 版本：Win 11 23H2 (或 Win 10 22H2)
- PowerShell：5.1 / 7.x
- Python：3.12.x (py -3 / python)
- Node.js：18.x (if tested server)
- 控制台编码：cp936 / UTF-8

## 跑过的命令
- [ ] -Mode collector -SkipScheduledTask
- [ ] -Mode server -SkipScheduledTask
- [ ] -Mode both -SkipScheduledTask
- [ ] -Mode both（含 scheduled task）

## 每一步结果
1. Python: OK / FAIL 原因
2. System Deps: OK / FAIL 原因
3. venv: OK / FAIL 原因
4. pip install: OK / FAIL 原因
5. Frontend: OK / SKIP / FAIL 原因
6. Configs: OK / FAIL 原因
7. Scheduled Tasks: OK / SKIP / FAIL 原因
8. Verify (每项 import): 逐条列出 OK / FAIL

## smoke test
- WindowsAdapter.get_frontmost_app() 输出：___
- winocr import：OK / FAIL

## 修改
- 你对 install.ps1 做的任何修改，贴 diff。
```

---

## 5. 不要越界的事

作者强调：**只做"环境 + 编译"的修复**，不要顺手改：

- `auto_daily_log/monitor/platforms/windows.py`（底层 WindowsAPI）—— 如果 smoke test 挂在这里，报告问题，不要改（那是 phase 2 的事）
- `install.sh`（Linux/macOS 装法）—— 风险蔓延
- `AGENTS.md` / `CLAUDE.md` —— 主线已经定好了，别改

**可以改**：`install.ps1` 本身、`docs/windows-install-hints.md`（这份文档）、`README.md` 里 Windows 安装章节。

---

## 6. 通过标准（一句话）

**任何 Windows 同事 clone 仓库，跑一条 `powershell -File install.ps1 ...`，10 分钟内看到"All checks passed"，venv 里能 `import auto_daily_log_collector`，smoke test 能打出当前前台 app 名字。**

达到这个就算交付。剩下的 scheduled task、adl.ps1、chat agent 不在本次范围。
