# FlorrVLM-Agent  Android APK 构建工程（buildozer）
# 用法：在此目录执行 buildozer -v android debug（自动装 SDK/NDK）
[app]
title = FlorrVLM-Agent
package.name = florrvlmagent
package.domain = org.florrvlm
source.dir = .
version = 1.9.0

requirements = python3,kivy

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = 0

presplash.filename =
icon.filename =

[buildozer]
log_level = 2
warn_on_root = 1

# 允许自动下载 Android SDK/NDK 许可与工具
android.accept_sdk_license = True