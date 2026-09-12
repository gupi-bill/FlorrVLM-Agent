# FlorrVLM-Agent  Android APK 壳（buildozer 配置）
# =================================================
# 说明：游戏智能体核心跑在桌面电脑上（依赖屏幕截图 / MCP / 本地文件）。
#       这里的 APK 是一个"手机端查看/遥控壳"，先能装能开给你看到产出物。
#       要真机遥控，需在此壳里接网络把桌面 agent 的状态推过来。
# 用法（在 Windows/Mac/Linux 装了 buildozer 后）：
#   buildozer -v android debug
# 首次会下载 Android SDK，需联网，约几百 MB。

[app]
title = FlorrVLM-Agent
package.name = florrvlmagent
package.domain = org.florrvlm
source.dir = .          # 会把仓库打进 app（也可只打 android_main.py）

version = 1.9.0

requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE

# 用 SDL2 原生窗口
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = armeabi-v7a, arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1