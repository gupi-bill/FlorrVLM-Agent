# Universal-Game-Framework 一键部署镜像（v2.0 · S12 与 requirements.txt 对齐）
# ==================================================================
# 构建: docker build -t ugf-agent .
# 运行: docker run --rm -it -v "$PWD/.env:/app/.env" ugf-agent
# 干跑: docker run --rm -e UGF_DRY_RUN=1 ugf-agent   # 只跑自检 + 启动流程，不碰键鼠
# 端口: 感知 5001 / 面板 5002（取自 config.yaml，与 start_all.sh 同一口径）
#
# 与 requirements.txt 的一致性约定：
#   - core 段全装（flask / requests / python-dotenv / pyyaml / psutil / mcp / numpy）
#   - opencv 在容器内强制换成 -headless（镜像内无 GUI，装 GUI 版会引入无用依赖链）
#   - pyautogui 保留：容器带 Xvfb，键鼠走虚拟屏仍可用
#   - 重度可选包（chromadb / sentence-transformers / PyQt6 / streamlit / kivy）不装：
#     体量大或强依赖 GUI，未装时代码自动走文本检索 / 离线降级分支
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TMPDIR=/tmp

WORKDIR /app

# 系统依赖（OpenCV 运行库 + 虚拟屏；尽量精简，构建后清理 apt 缓存）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    xvfb x11-utils \
    && rm -rf /var/lib/apt/lists/*

# 项目依赖：requirements.txt 是唯一真源，容器内只做「opencv → headless」一处替换
COPY requirements.txt .
RUN sed -e 's/^opencv-python>=.*/opencv-python-headless>=4.8.0/' requirements.txt > /tmp/req.txt \
    && pip install --no-cache-dir -r /tmp/req.txt \
    && rm -f /tmp/req.txt

# 项目代码（排除本地运行数据，见 .dockerignore）
COPY . .

EXPOSE 5001 5002

# 默认命令：虚拟屏 → 启动自检（WARN 只降级不阻断）→ 看门狗拉起 Agent。
# UGF_DRY_RUN=1 时透传给 agent_main：不碰真实键鼠、不调外部 LLM，可离线验证链路。
CMD ["bash", "-c", \
     "Xvfb :99 -screen 0 1920x1080x24 & export DISPLAY=:99 UGF_FOREGROUND=1; \
      python boot_check.py --fail-fast && exec bash start_all.sh"]
