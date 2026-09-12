@echo off
rem ============================================================
rem  FlorrVLM-Agent  Windows 打包（EXE + 免安装便携版）
rem  在 Windows 上运行： build_windows.bat
rem  产出：
rem    dist_win\florrvlm-agent\       可执行目录(=免安装便携版，拷走即可用)
rem    dist_win\florrvlm-agent-portable.zip   便携版压缩包
rem    dist_win\florrvlm-agent.exe    单文件 EXE
rem ============================================================
setlocal
cd /d "%~dp0.."
if not exist venv (
  python -m venv venv
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller

echo [1/4] 清理旧产物
if exist dist_win rmdir /s /q dist_win
if exist build rmdir /s /q build

echo [2/4] 打可执行目录(=免安装便携版) + 单文件 EXE
python -m PyInstaller --noconfirm --clean --onedir --name florrvlm-agent agent_cli.py
python -m PyInstaller --noconfirm --clean --onefile --name florrvlm-agent-exe agent_cli.py

echo [3/4] 组装便携版目录：exe + 数据文件
if exist "dist_win" rmdir /s /q dist_win
move dist\florrvlm-agent dist_win
if not exist dist_win\game_profiles  xcopy /e /i /y game_profiles dist_win\game_profiles
if not exist dist_win\skills        xcopy /e /i /y skills       dist_win\skills
copy /y mcp_connectors.yaml config.yaml dist_win\
copy /y dist\florrvlm-agent-exe.exe dist_win\florrvlm-agent.exe
del /q dist\florrvlm-agent-exe.exe

echo [4/4] 打便携 zip
powershell -NoProfile -Command "Compress-Archive -Path dist_win -DestinationPath dist_win\florrvlm-agent-portable.zip -Force"

echo.
echo 完成: 便携版 = dist_win（zip: dist_win\florrvlm-agent-portable.zip）；EXE = dist_win\florrvlm-agent.exe
echo 免安装：把 dist_win 文件夹拷到任意电脑双击 florrvlm-agent.exe 即可(需装 Python 运行库)
endlocal