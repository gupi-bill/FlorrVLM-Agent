# OPS.md · 运维脚本与容器一致性（S12）

> 目标：`start_all.sh` / `stop_all.sh` / `watchdog.sh` / `Dockerfile` / `boot_check.py`
> 五者口径一致，且在**无 GUI / 无 X server / 无 YOLO 权重 / 无 API Key** 的本机可干跑。

## 一、五件套职责与口径

| 文件 | 职责 | 关键口径 |
|---|---|---|
| `boot_check.py` | 启动自检（分级：ERROR 阻断 / WARN 降级） | 依赖分级、端口、运维引用一致性 |
| `start_all.sh` | 拉起 4 个服务（感知/MCP/Agent/面板） | 端口读 `config.yaml`，不写死 |
| `stop_all.sh` | 停进程 + 清 `video_frames/` + 日志轮转 | `UGF_LOG_KEEP_DAYS`（默认 7 天） |
| `watchdog.sh` | Agent 崩溃自愈（退避重启 + 内存上限） | `UGF_PYTHON` / `UGF_DRY_RUN` 透传 |
| `Dockerfile` | 容器镜像（Xvfb + headless 依赖） | opencv 强制 `-headless`，`EXPOSE 5001 5002` |

**端口唯一真源**：`config.yaml` → `perception_port: 5001` / `panel_port: 5002`。
三个 shell 脚本全部通过 `port_of()` 现读，`boot_check.check_ops()` 反向校验脚本里
若出现端口字面量必须与 config 一致（不一致 → ERROR）。

## 二、环境变量（全线通用）

| 变量 | 默认 | 作用 |
|---|---|---|
| `UGF_PYTHON` | 自动探测 `python3`/`python` | 指定解释器（本机隔离 venv 必填） |
| `UGF_DRY_RUN` | `0` | `1`=干跑：不起进程、不碰键鼠、不调外部 LLM；子进程自动继承 |
| `UGF_FOREGROUND` | `0` | `1`=start_all 挂住 agent 进程（容器 CMD 使用，否则容器立刻退出） |
| `UGF_LOG_KEEP_DAYS` | `7` | 日志保留天数，`<=0` 表示不清理 |
| `AGENT_GAME` / `UGF_GAME` | `config.yaml` 的 `agent.game` | 临时切换游戏档案 |

## 三、命令速查

```bash
export UGF_PYTHON=/home/g-bill/.workbuddy/binaries/python/envs/ugf/bin/python

python boot_check.py                # 人读报告（WARN 不阻断）
python boot_check.py --strict       # CI/容器门禁：WARN 也退出 1
python boot_check.py --json         # 机器可读
python boot_check.py --no-ops       # 跳过运维脚本一致性检查

bash start_all.sh --dry-run         # 干跑全流程（退出码 0，无副作用）
bash start_all.sh --no-check        # 跳过自检
bash start_all.sh --help
bash stop_all.sh --dry-run          # 只打印将 kill / 将删除什么
bash stop_all.sh --keep-logs        # 保留日志
bash watchdog.sh --max-mem=1G       # 带内存上限的崩溃自愈

docker build -t ugf-agent .
docker run --rm -e UGF_DRY_RUN=1 ugf-agent     # 容器内离线干跑
```

## 四、离线降级矩阵（本机实测）

| 缺失项 | 旧行为 | v2.0 行为 | 降级路径 |
|---|---|---|---|
| `cv2` | **ERROR → 启动被拦** | WARN | 视频学习/图像处理不可用；主链路不受影响 |
| `PIL` | **ERROR → 启动被拦** | WARN | 感知走 mock 帧（numpy 合成） |
| `pyautogui` | ERROR | WARN | 动作只记录不下发（`UGF_DRY_RUN=1`） |
| 无 X server | 未检查 | WARN | 提示 `Xvfb :99`；自动 mock + dry-run |
| 无 YOLO 权重 | 未检查 | WARN | 目标检测不可用，改用档案 `perception.mock` 实体 |
| 无 `.env` | WARN（无指引） | WARN + 降级说明 | 不调外部 LLM/VLM，规则兜底 |

设计依据：本机上述 6 项**全部缺失**，旧版 `start_all.sh --fail-fast` 会 100% 退出，
导致"离线链路根本起不来" —— 与项目「任意 2D 游戏可离线接入」的定位冲突。

## 五、运维一致性自检（`boot_check.check_ops()`）

1. 脚本引用的文件必须存在（`start_all.sh` → 4 个 py；`watchdog.sh` → `agent_main.py`；
   `Dockerfile` → `requirements.txt` / `boot_check.py` / `start_all.sh`）。
2. 脚本/文档中的 `perception_port` / `panel_port` 字面量必须与 `config.yaml` 一致。
3. 该检查并入 `boot_check.py` 默认流程，`tests/test_ops.py` 用"临时删文件"反向用例
   锁定校验器自身不失效。

## 六、验收结果（2026-09-21 S12）

- `bash start_all.sh --dry-run` → 退出码 0，打印 5001/5002，未创建任何 `.pid` ✅
- `UGF_DRY_RUN=1 bash start_all.sh` 与 `--dry-run` 等价 ✅
- `bash stop_all.sh --dry-run` → 退出码 0；沙箱实测：删 `video_frames/`、轮转过期日志、
  保留未过期日志、清 `*.tmp` ✅
- `python boot_check.py` → ERROR 0 / WARN 6（含图形环境、权重、.env、3 个可选库），
  退出码 0 且每条 WARN 都带降级指引 ✅
- `python boot_check.py --strict` → 退出码 1（WARN 视为阻断，供容器门禁）✅
- `tests/test_ops.py` 21 用例全绿；全量 `pytest` 见 PROGRESS.md ✅

## 七、遗留

- 容器镜像未在本机构建验证（无 docker / 无网络拉取基础镜像），仅做静态口径对齐与
  `opencv-python-headless` 替换；真实 `docker build` 需在有 docker 的环境补验。
- `stop_all.sh` 只按 mtime 轮转 `run_logs/`，未按体积封顶；磁盘紧张场景可再加
  `UGF_LOG_MAX_MB` 上限。
- 真实（非 dry-run）启停在无 GUI 机器上仍会启动面板/感知进程，需在宿主机验证一次。
