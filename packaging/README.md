# FlorrVLM-Agent 系统安装包（v1.9）
====================================

把整套引擎打成可直接安装/运行的安装包。四种平台，产出如下：

| 平台 | 产物 | 在哪打 | 状态 |
|------|------|--------|------|
| Linux .deb | `dist/florrvlm-agent_<ver>_amd64.deb` | 本机（Linux） | ✅ 可直接打 |
| Linux 免安装 | `dist/florrvlm-agent_<ver>_portable.tar.gz` | 本机（Linux） | ✅ 可直接打 |
| Windows EXE / 便携 | `dist_win/florrvlm-agent.exe` + `-portable.zip` | Windows | 需在 Windows 跑 bat |
| Android APK | `florrvlm-agent-1.9.0-*.apk` | 任意装 buildozer 的机器 | 需 buildozer |

## 沙箱内构建状态（自动化环境实测）
- `deb` / `portable`：✅ 已在沙箱内真实产出并运行。
- `buildozer` APK：❌ 沙箱出网连 `skia.googlesource.com`（Kivy 编译需拉 skcms 子模块）
  会 TLS 握手失败，被防火墙阻挡。构建工程本身已就绪，请在有外网直连该主机的地方跑：
  `cd packaging/androidapp && yes | buildozer -v android debug`。
- `wine` EXE：✅ 已在沙箱用 Wine + Windows Python + PyInstaller 交叉产出
  `dist_win/florrvlm-agent.exe`，并已验证能启动、能跑命令、中文正常。

---

## 1. Linux .deb（推荐，一键装）
```bash
python tools/build_dist.py deb
sudo apt install -y ./dist/florrvlm-agent_1.9.0_amd64.deb
florrvlm-agent          # 装完直接有命令，进入交互 CLI
florrvlm-agent -c report    # 或跑单条命令
```
文件装到 `/usr/lib/florrvlm-agent/`，命令软链到 `/usr/bin/florrvlm-agent`。
依赖：`python3 python3-yaml python3-requests python3-dotenv`（缺 `mcp` 等可选包时，
部分能力(外接 MCP)不可用，核心本地玩法仍可用）。

## 2. Linux 免安装便携版（绿色版，解压即用）
```bash
python tools/build_dist.py portable
tar -xzf dist/florrvlm-agent_1.9.0_portable.tar.gz
cd florrvlm-agent && ./florrvlm-agent
```
不写系统、不装依赖（需系统装 python3 + PyYAML、requests、dotenv）。

## 3. Windows（.exe / 免安装便携版）
在 **Windows** 上双击运行 `packaging/build_windows.bat`，需要已装 Python 3.9+。
自动：
- 建 `venv`、装依赖 + PyInstaller
- 生成可执行目录 = **免安装便携版**（拷到任何电脑即可用）
- 打成 `florrvlm-agent-portable.zip`
- 再出单文件 `florrvlm-agent.exe`

## 4. Android（.apk）
在任意系统装 buildozer 后：
```bash
cd florrvlm-agent   # 需要把 android_main.py、buildozer.spec 放在一起
cp packaging/buildozer.spec packaging/android_main.py .
buildozer -v android debug
```
> 说明：完整智能体依赖桌面屏幕截图/MCP。这里提供的 APK 是一个可安装、可打开的
> **手机展示壳**（展示玩法与包信息）。要真机打手游，需再接入屏幕/输入驱动，见 ROADMAP。

---

## 常用
```bash
python tools/build_dist.py all        # 一次打 deb + 便携
python tools/build_dist.py deb        # 只打 deb
python tools/build_dist.py portable   # 只打便携
```
版本号默认 `1.9.0`，可 `export PKG_VERSION=2.0.0` 覆盖。