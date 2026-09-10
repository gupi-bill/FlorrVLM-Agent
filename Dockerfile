# FlorrVLM-Agent 一键部署镜像（v1.0）
# ==================================
# 构建: docker build -t florr-agent .
# 运行: docker run --rm -it -v "$PWD/.env:/app/.env" florr-agent
# 说明: 游戏自动打还需要图形/键鼠环境，镜像提供完整的 Python 运行环境
#       + 启动自检；接显示器/键鼠(如 Xvfb + pyautogui)由宿主机提供。

FROM python:3.11-slim

WORKDIR /app

# 系统依赖（OpenCV/键鼠所需基础库，尽量精简）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    xvfb x11-utils \
    && rm -rf /var/lib/apt/lists/*

# 项目依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 项目代码（排除本地产生的运行数据，见 .dockerignore）
COPY . .

# 默认命令：先自检，通过则以 Xvfb 虚拟屏幕 + 看门狗启动 Agent
CMD ["bash", "-c", \
     "Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99; \
      python boot_check.py --fail-fast && exec bash watchdog.sh"]