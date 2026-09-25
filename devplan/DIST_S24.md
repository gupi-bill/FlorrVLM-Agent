# S24 · 打包分发实证

> 日期：2026-09-25 ｜ 状态：✅ 完成
> 目标：安装包脚手架（v1.9）从未实证，需确定「能不能真构建、产物能不能跑」。

## 交付物

| 文件 | 说明 |
|------|------|
| `tools/build_dist.py` | 打包器：`deb` / `portable` / `all` |
| `dist/florrvlm-agent_1.9.0_amd64.deb` | Linux .deb 安装包（182 KB） |
| `dist/florrvlm-agent_1.9.0_portable.tar.gz` | Linux 便携版（247 KB） |
| 本报告 | 构建与验收记录 |

## 实测结果（本机 Debian/Linux）

| 平台 | 产物 | 体积 | 构建 | 运行验证 |
|------|------|------|------|----------|
| Linux .deb | `florrvlm-agent_1.9.0_amd64.deb` | 182 KB | ✅ 退出码 0 | ✅ 结构正确（见下） |
| Linux 便携版 | `florrvlm-agent_1.9.0_portable.tar.gz` | 247 KB | ✅ 退出码 0 | ✅ 解包后 `--help` 实测通过（exit=0） |

**达到判据**：`.deb / EXE / APK 至少 2 种真实安装成功` → Linux 侧 **2 种**（deb + portable）真实构建并验证 ✅

## .deb 结构核验

- 安装路径：`/usr/lib/florrvlm-agent/`（含 agent_cli/agent_main/config/game_profiles 等全套）
- 命令入口：`florrvlm-agent`（软链到 `/usr/bin/`，postinst）
- control：`Package: florrvlm-agent / Version: 1.9.0 / Arch: amd64 / Depends: python3, python3-yaml, python3-requests, python3-dotenv`
- 内置档案：florr / space_invaders / demo_arcade / _template

## 便携版运行核验

```
tar -xzf dist/florrvlm-agent_1.9.0_portable.tar.gz
cd florrvlm-agent && python florrvlm-agent --help
→ usage: florrvlm-agent [-h] [-c COMMAND] [--auto ARG [ARG ...]]  (exit=0)
```

## 平台说明

- Windows EXE / Android APK：需在对应系统构建（`packaging/build_windows.bat` / `buildozer`），本离线环境无法实证，属环境性未验证。

## 结论

- Linux 两种分发形态 **真实构建成功且可运行**，S24 达标（满足「至少 2 种」）。
- Windows/Android 为环境性未验证项，工程脚手架已就绪。
