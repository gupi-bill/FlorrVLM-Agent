# Universal-Game-Framework 定时推进 · 自动化配置（手动建到 WorkBuddy 面板）

> 用途：让 WorkBuddy 服务端每 30 分钟自动推进 `devplan/PLAN_NIGHT_0924.md` 的一个格子。
> 服务端持有 = 沙箱重置也不丢，比会话内循环稳。
> 本会话 `automation_update` 工具不可用，所以这份配置由你在「自动化」面板手动新建。

---

## 一、名称建议
`UGF 夜间计划推进（每30分钟）`

## 二、调度（二选一，看面板支持哪种粒度）

### 方案 A：面板支持「每 N 分钟」粒度（首选）
- 周期类型：recurring
- 周期：每 30 分钟
- 或 rrule 文本框填：`FREQ=MINUTELY;INTERVAL=30`
- validFrom：今天（如 2026-09-24 00:00）；validUntil：留空（长期）

### 方案 B：面板只支持小时级（稳妥兜底，必成）
建 **两条** recurring 自动化，都是 `FREQ=HOURLY;INTERVAL=1`，靠 validFrom 错峰，合起来=每30分钟。
> 注意：RRULE 不支持 `BYMINUTE=0,30` 这种逗号多值，必须拆两条。

- 条 1：`FREQ=HOURLY;INTERVAL=1`  validFrom=`2026-09-24 00:00`
- 条 2：`FREQ=HOURLY;INTERVAL=1`  validFrom=`2026-09-24 00:30`
- 两条 validUntil 都留空（长期）

---

## 三、任务 Prompt（粘进 prompt 字段，已自包含，未来 agent 看不到本对话）

```
你是 Universal-Game-Framework 项目的定时推进 agent。

【项目位置】
- 本地路径：/home/g-bill/文档/Default Project/Universal-Game-Framework
- 远端仓库：github.com/gupi-bill/Universal-Game-Framework（分支 main）
- Python venv：/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python
- 本机约束：/tmp 仅 10M（命令前置 TMPDIR=/home/g-bill/.workbuddy/tmp）；无 GUI（键鼠只能 dry-run，设 UGF_DRY_RUN=1）；推 GitHub 需绕代理 env -u http_proxy -u https_proxy -u HTTPS_PROXY git push。

【每次触发执行步骤】
1. 读 devplan/NEXT_SLOT 拿当前格子编号（如 S4）。
2. 读 devplan/PLAN_NIGHT_0924.md 里该格子的具体任务说明。
3. 用 venv 完成该格子任务（写文件 / 修 bug / 补文档 / 跑测试等）。
4. 全量测试门禁（必须绿才提交）：
   TMPDIR=/home/g-bill/.workbuddy/tmp timeout 240 /home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python -m pytest tests/ -q
5. 完成后在 PROGRESS.md 标注该格 done，并把 devplan/NEXT_SLOT 推进到下一格（超过 S15 回 S1 循环）。
6. 提交并推远端：
   git add -A && git commit -q -m "cron: <格子> <一句话>" && env -u http_proxy -u https_proxy -u HTTPS_PROXY timeout 90 git push origin main
7. 把本次执行摘要（做了啥、测试结果、是否推动指针）追加到 devplan/CRON_LOG.md。

【硬性约束】
- 不删除任何文件、不改远端仓库结构；危险操作先说明再动。
- S1（GitHub Release）需要 GitHub PAT/gh 登录，本环境没有 → 标记 deferred 跳过，不要卡住。
- 若某格子依赖外部资源（token/网络）拿不到，标记 deferred 并写清原因，继续下一格，不要空转报错。
- 每轮只推进一个格子；只有当该格在 PROGRESS.md 标记 done 时才推进 NEXT_SLOT。
```

---

## 四、建好后验证
建完告诉我，我可以用 `git log` / `devplan/CRON_LOG.md` 帮你确认它是否真的在按 30 分钟节奏推进。

## 五、备注
- 当前会话内另有兜底循环 `cron_loop.sh`（task cgb3sg 在跑），沙箱重置会丢；面板自动化建好后，会话内这条可留可删，互不冲突。
- 若以后 `automation_update` 工具恢复，可直接用工具建，prompt 同上。
