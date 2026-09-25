#!/usr/bin/env bash
# 真机（G-Bill 桌面）启用检查 —— 用于 S18 真机 A/B 前置
# 用法：在【桌面终端】里运行  bash tools/enable_realmachine.sh
set -u
PY="$HOME/.workbuddy/binaries/python/envs/ugf/bin/python"
ok=0; miss=0
chk(){ if [ "$1" = 0 ]; then echo "  ✅ $2"; ok=$((ok+1)); else echo "  ❌ $2"; miss=$((miss+1)); fi; }

 echo "===== 真机链路检查 ====="

 # 1) 桌面会话变量
 [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; chk $? "图形会话变量 (DISPLAY/WAYLAND_DISPLAY)"
 [ -S "/run/user/$(id -u)/bus" ]; chk $? "session DBus (/run/user/$(id -u)/bus)"

 # 2) 系统工具
 command -v xdotool        >/dev/null; chk $? "xdotool（键鼠操作）"
 command -v gnome-screenshot >/dev/null; chk $? "gnome-screenshot（GNOME 截图）"

 # 3) Python 库（venv）
 [ -x "$PY" ] && "$PY" -c 'import PIL' >/dev/null 2>&1; chk $? "PIL (pillow)"
 [ -x "$PY" ] && "$PY" -c 'import cv2' >/dev/null 2>&1; chk $? "cv2 (opencv)"
 [ -x "$PY" ] && "$PY" -c 'import mss' >/dev/null 2>&1; chk $? "mss"
 [ -x "$PY" ] && "$PY" -c 'import pyautogui' >/dev/null 2>&1; chk $? "pyautogui"

 # 4) 密钥 / 权重 / 游戏
 [ -f "$PWD/.env" ]; chk $? ".env 密钥"
 ls "$PWD"/*.pt >/dev/null 2>&1; chk $? "YOLO 权重 (*.pt)"

 # 5) 截图实测（触发 portal 授权，会弹窗，需点“允许”）
 echo "  … 测试截图（可能弹授权框）"
 if command -v gnome-screenshot >/dev/null; then
   gnome-screenshot -f /tmp/ugf_shot.png 2>/dev/null && [ -s /tmp/ugf_shot.png ]
   chk $? "截图落地 /tmp/ugf_shot.png"
 fi

 echo
 echo "===== 结果：✅ $ok 项就绪 / ❌ $miss 项待补 ====="
 [ $miss -eq 0 ] && echo "🎉 真机链路就绪，可以跑 S18 真机 A/B" || echo "按上面 ❌ 项补齐后重跑本脚本"
