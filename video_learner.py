#!/usr/bin/env python3
"""
FlorrVLM-Agent 视频学习模块 video_learner.py
==============================================
读取本地 florr.io 教程视频，逐帧 VLM 提取战术，写入 Markdown 知识库。

注意：
- 教程视频需要用户自行下载放到本地，本程序不会联网下载视频
- 每帧处理完立刻删除图片，全部结束后清理整个临时目录
- Ctrl+C 中断时自动清理临时文件，不残留垃圾
- 战术存入 knowledge_md/*.md，永久保留

用法:
    python video_learner.py ./florr_tutorial.mp4
    python video_learner.py ./florr_tutorial.mp4 --skip 30
"""
import argparse
import base64
import os
import signal
import sys
import time
from datetime import datetime

import cv2
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
VLM_API_URL = os.getenv("VLM_API_URL", "")
VLM_API_KEY = os.getenv("VLM_API_KEY", "")
VLM_MODEL = os.getenv("VLM_MODEL", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE_DIR, "knowledge_md")
FRAME_DIR = os.path.join(BASE_DIR, "video_frames")
os.makedirs(KB_DIR, exist_ok=True)

VLM_PROMPT = """你正在观看 florr.io 游戏教程视频的一帧画面。
请仔细观察：玩家使用的花瓣组合、面对的怪物/BOSS、走位方式、操作意图。
提炼一条可复用的游戏战术，用一句话输出，不要多余解释。"""


# ---------------------------------------------------------------------------
# 临时文件清理（Ctrl+C 信号捕获）
# ---------------------------------------------------------------------------
def cleanup_temp_frames():
    """删除全部临时帧文件和目录。"""
    import shutil
    if os.path.exists(FRAME_DIR):
        try:
            shutil.rmtree(FRAME_DIR, ignore_errors=True)
            print(f"\n[清理] 已删除临时帧目录 {FRAME_DIR}")
        except Exception as e:
            print(f"[清理] 删除失败: {e}")


def _signal_handler(signum, frame):
    """捕获 Ctrl+C，先清理临时文件再退出。"""
    print("\n[中断] 收到中断信号，正在清理临时文件...")
    cleanup_temp_frames()
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------
def extract_frames(video_path: str, skip: int = 25) -> list:
    """从视频中按间隔抽帧，返回帧文件路径列表。"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"错误: 无法打开视频 {video_path}")
        sys.exit(1)

    os.makedirs(FRAME_DIR, exist_ok=True)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"视频信息: {total} 帧, {fps:.1f} FPS, 每 {skip} 帧抽一张")

    frames = []
    idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if idx % skip == 0:
            save_path = os.path.join(FRAME_DIR, f"frame_{idx:06d}.jpg")
            cv2.imwrite(save_path, frame)
            frames.append(save_path)
        idx += 1
    cap.release()
    print(f"共抽取 {len(frames)} 帧")
    return frames


def image_to_base64(img_path: str) -> str:
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def vlm_extract_tactic(b64_img: str) -> str:
    """调用 VLM API 从单帧画面提取战术文本。"""
    if not VLM_API_URL or not VLM_API_KEY:
        return "[未配置 VLM_API_URL / VLM_API_KEY，跳过 API 调用]"

    headers = {
        "Authorization": f"Bearer {VLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                    {"type": "text", "text": VLM_PROMPT},
                ],
            }
        ],
        "max_tokens": 200,
    }

    try:
        resp = requests.post(VLM_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[VLM 调用失败: {e}]"


def save_tactics_to_kb(video_name: str, tactics: list):
    """把提取到的全部战术写成一个 Markdown 文件存入知识库。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"video_tactic_{os.path.splitext(video_name)[0]}_{timestamp}.md"
    filepath = os.path.join(KB_DIR, filename)

    content = f"# 视频学习战术 — {video_name}\n\n"
    content += f"> 学习时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    content += f"> 提取帧数: {len(tactics)}\n\n"
    content += "## 战术列表\n\n"
    for i, t in enumerate(tactics, 1):
        content += f"{i}. {t}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n已保存 {len(tactics)} 条战术到知识库: {filename}")
    return filename


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FlorrVLM-Agent 视频战术学习")
    parser.add_argument("video", help="本地教程视频文件路径 (mp4)，程序不会自动下载网络视频")
    parser.add_argument("--skip", type=int, default=25, help="抽帧间隔，默认 25")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"错误: 视频文件不存在 {args.video}")
        print("提示: 请自行下载教程视频到本地，再传入路径")
        sys.exit(1)

    print("=" * 55)
    print("  FlorrVLM-Agent 视频学习模块")
    print("  教程视频需用户本地自备，程序不联网下载")
    print("=" * 55)

    # 1. 抽帧
    frames = extract_frames(args.video, skip=args.skip)

    # 2. 逐帧 VLM 提取战术，处理完一帧立刻删一帧
    tactics = []
    try:
        for i, fp in enumerate(frames, 1):
            b64 = image_to_base64(fp)
            tactic = vlm_extract_tactic(b64)
            tactics.append(tactic)
            print(f"[{i}/{len(frames)}] {tactic[:60]}")

            # 处理完立刻删除该帧
            try:
                os.remove(fp)
            except OSError:
                pass

            time.sleep(0.3)  # 避免 API 限流
    finally:
        # 无论正常结束还是异常，都清理整个临时目录
        cleanup_temp_frames()

    # 3. 写入知识库（md 保留，不删除）
    save_tactics_to_kb(os.path.basename(args.video), tactics)
    print("\n视频学习完成！战术已存入 knowledge_md/，临时帧已全部清理。")


if __name__ == "__main__":
    main()
