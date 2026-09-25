# S28 · 真机环境勘察（这台机器 = 真机）

> 日期：2026-09-25 ｜ 状态：勘察完成 ｜ 机器：G-Bill（Debian Linux）
> 背景：用户指定「真机环境就用这个」。本文如实记录这台机器**具备/缺失**的真机条件。

## ✅ 具备（比我此前假设的「无头」强得多）

| 能力 | 实测 |
|------|------|
| **真实图形会话** | ✅ GNOME on **Wayland** 活着（`gnome-shell` PID 1044，已跑 88min，会话 session 1 活跃） |
| **真实屏幕** | ✅ 1366×768（`xdpyinfo` 连上 `:0` 读到 dimensions） |
| **X 显示** | ✅ Xwayland `:0`（rootless）；`DISPLAY=:0`，`XAUTHORITY=/run/user/1000/.mutter-Xwaylandauth.LOAHW3` |
| **桌面 portal** | ✅ `xdg-desktop-portal` + `-gnome` + `-gtk` 在跑 |
| **截图工具链** | ✅ `xdpyinfo` / `import` / `convert` / `xwd` 已安装 |
| 登录会话 | ✅ g-bill 在 seat0 / tty2 |

> 意义：**FUTURE §2.2 里「无 X server」的假设被推翻**——这台机器有真实桌面。

## ❌ 缺失（要跑真机 A/B 还需补齐）

| 缺口 | 现状 | 补齐方式 |
|------|------|----------|
| 真实截图落地 | Xwayland rootless → `import`/`xwd` 抓 root 失败；portal 截图返回了 request 对象但**需桌面交互授权** | 在**本机桌面**上跑授权，或用 `grim`（Wayland）| 
| 键鼠操作 | `xdotool`/`pyautogui` **未装** | `apt install xdotool` / `pip install pyautogui` |
| 视觉库 | `PIL`/`cv2` **未装**（仅 numpy） | `pip install pillow opencv-python-headless` |
| LLM/VLM 密钥 | `.env` **不存在** | 填密钥 |
| YOLO 权重 | `ultralytics` **未装**、无 `*.pt/*.onnx` | 装 ultralytics + 下载权重 |
| 真实游戏窗口 | **未运行** | 打开 florr.io / space_invaders |

## 结论

**这台机器是真机（有真桌面、真屏幕），但当前还缺「游戏 + 感知/输入依赖 + 密钥/权重」。**

- 能力侧：显示与 portal 就绪 → 一旦补上依赖和游戏，**截图/键鼠链路具备落地条件**。
- 我这侧（headless shell）：能连 X 读元信息，但**抓不到像素**（Wayland rootless + portal 需交互授权），也**无法操作键鼠**（依赖未装）。

## 建议下一步（按依赖顺序）

1. `apt install xdotool grim` + `pip install pillow opencv-python-headless pyautogui`
2. 打开一个游戏窗口（先 space_invaders 类的自建/开源，合规）
3. 本机桌面上授权一次 portal 截图 → 验证「能截到真实像素」
4. 装 ultralytics + 权重 → 真实 YOLO 感知
5. 至此可跑 **S18 真机 A/B**（基线组 vs 学习组真实胜率 + Bootstrap）

> 上述 1~4 属**环境安装 + 人机交互**，需在你的桌面会话里执行；5 可由我在依赖就绪后驱动。

---

## 附：依赖安装实测（2026-09-25 由 AI 尝试）

### ✅ 装成功（Python 侧，无需 sudo）
| 包 | 结果 |
|----|------|
| pillow 12.3.0 | ✅ 已装（venv 可见） |
| opencv-python-headless 5.0.0.93 | ✅ 已装 |
| mss 10.2.0 | ✅ 已装 |

### ⚠️ 装了但 venv 不可见
| 包 | 现象 |
|----|------|
| pyautogui + python-xlib 等依赖 | pip 报 Successfully installed，但装到了 **user site** `/home/g-bill/.local/lib/python3.13/site-packages`，而 venv（`~/.workbuddy/.../ugf`）隔离，import 仍失败 |

> 修：在该 venv 里 `pip install --force-reinstall pyautogui`，或 `PYTHONPATH=$HOME/.local/lib/python3.13/site-packages` 注入。

### ❌ 装不了（需 sudo 密码）
| 工具 | 原因 |
|------|------|
| xdotool / grim / scrot | `sudo: 需要密码`，AI 无法提权 |

> 修：你在本机终端 `sudo apt install -y xdotool grim`。

### 截图链路结论（决定性）
| 路径 | 结果 |
|------|------|
| X11 `import`/`xwd`/`mss` 抓 root | ❌ BadMatch / XProtoError（**Xwayland rootless 不允许抓 root window**）|
| `gnome-shell` DBus 截图 | ❌ `AccessDenied: Screenshot is not allowed`（mutter 安全策略）|
| `xdg-desktop-portal` 截图 | ⚠️ 返回 request 对象，但**需桌面交互授权**（AI 点不了授权框）|
| `xwininfo -root -tree` 读窗口树 | ✅ 可读（只有 Fcitx 输入窗，无游戏窗口）|

### 还没做（需人类输入）
- `.env` 密钥：AI 没有、也不应编造
- YOLO 权重：需指定模型（ultralytics 未装）
- 开游戏窗口：需 GUI 操作

### 结论
AI 能把**纯 Python 感知库**装好（pillow/opencv/mss），但：
1. 系统级工具（xdotool/grim）与 **pyautogui 的 venv 可见性**需人类一步；
2. **真截图必须经 portal 授权**（Wayland 安全模型），AI 无法代点；
3. 密钥/权重/游戏窗口属人类职责。
补齐后即可跑 S18 真机 A/B。
