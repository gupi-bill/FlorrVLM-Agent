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
    python video_learner.py ./florr_tutorial.mp4          # 本地视频学习
    python video_learner.py --auto --query "florr.io教程"  # 自动搜索下载再学（需 yt-dlp）
"""
import argparse
import base64
import difflib
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime

import cv2
import requests
from dotenv import load_dotenv

import video_sources

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


# ---------------------------------------------------------------------------
# v0.4 自动下载 + 知识库去重
# ---------------------------------------------------------------------------
def download_video(url: str, dest_dir: str) -> str:
    """用 yt-dlp 下载视频到 dest_dir，返回本地路径（学完由主流程删除）。"""
    os.makedirs(dest_dir, exist_ok=True)
    out_tmpl = os.path.join(dest_dir, "auto_%(id)s")
    try:
        subprocess.run(
            ["yt-dlp", "-f", "b[ext=mp4]/bv*+ba/b", "-o", out_tmpl + ".%(ext)s",
             "--merge-output-format", "mp4", url],
            capture_output=True, text=True, timeout=300,
        )
    except Exception as e:
        return f"下载失败: {e}"
    # 找刚下载的文件
    cands = [os.path.join(dest_dir, f) for f in os.listdir(dest_dir)
             if f.endswith(".mp4")]
    return cands[0] if cands else "下载失败：未得到视频文件"


def _dedup_new(tactics: list, ratio_threshold: float = 0.75) -> list:
    """
    v0.4 知识库去重：把与历史 video_tactic_*.md 里已有战术过于相似的新条目剔除，
    只保留真正的新战术，避免知识库膨胀。
    """
    known = []
    for f in os.listdir(KB_DIR):
        if not (f.startswith("video_tactic_") and f.endswith(".md")):
            continue
        with open(os.path.join(KB_DIR, f), "r", encoding="utf-8") as fh:
            known.append(fh.read())
    known_blob = "\n".join(known)

    # 剔除无意义的占位/失败提示
    def _useful(t):
        return len(t) > 4 and not t.startswith("[") and not t.startswith("（")

    out = []
    for t in tactics:
        if not _useful(t):
            continue
        if len(t) >= 5 and difflib.SequenceMatcher(None, t, known_blob).ratio() >= ratio_threshold:
            continue  # 与已有知识太像，跳过
        out.append(t)
    return out


def save_tactics_to_kb(video_name: str, tactics: list):
    """把提取到的全部战术写成一个 Markdown 文件存入知识库（含去重）。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"video_tactic_{os.path.splitext(video_name)[0]}_{timestamp}.md"
    filepath = os.path.join(KB_DIR, filename)

    kept = _dedup_new(tactics)
    content = f"# 视频学习战术 — {video_name}\n\n"
    content += f"> 学习时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    content += f"> 提取帧数: {len(tactics)}，去重后 {len(kept)} 条\n\n"
    content += "## 战术列表\n\n"
    for i, t in enumerate(kept, 1):
        content += f"{i}. {t}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n已保存 {len(kept)} 条新战术到知识库: {filename}")
    return filename


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FlorrVLM-Agent 视频战术学习")
    parser.add_argument("video", nargs="?", default=None,
                        help="本地教程视频文件路径 (mp4)")
    parser.add_argument("--auto", action="store_true",
                        help="自动搜索并下载教程视频（需 yt-dlp）")
    parser.add_argument("--query", default="", help="自动搜索用的查询词")
    parser.add_argument("--skip", type=int, default=25, help="抽帧间隔，默认 25")
    args = parser.parse_args()

    print("=" * 55)
    print("  FlorrVLM-Agent 视频学习模块")
    print("=" * 55)

    # v0.4 自动获取：搜索 → 下载 → 学完删源文件
    video_path = args.video
    if args.auto:
        if not args.query:
            print("错误: --auto 模式需要 --query 指定搜索词")
            sys.exit(1)
        results = video_sources.search_videos(args.query)
        title, url = results[0]
        print(f"[搜索] 命中: {title} | {url}")
        if not url or "未" in title:
            print("没有可用的视频来源（未安装 yt-dlp 或搜索失败）。")
            print("可先 pip/手动安装 yt-dlp，或直接把视频传到本地再运行本脚本。")
            sys.exit(1)
        os.makedirs(FRAME_DIR, exist_ok=True)
        video_path = download_video(url, FRAME_DIR)
        if video_path.startswith("下载失败"):
            print(f"[下载] {video_path}")
            cleanup_temp_frames()
            sys.exit(1)
        print(f"[下载] 已下载到 {video_path}")

    if not video_path or not os.path.exists(video_path):
        print(f"错误: 视频文件不存在 {video_path}")
        print("用法: python video_learner.py ./tutorial.mp4")
        print("  或: python video_learner.py --auto --query \"florr.io教程\"")
        sys.exit(1)

    # 1. 抽帧
    frames = extract_frames(video_path, skip=args.skip)

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
        # 无论正常结束还是异常，都清理整个临时目录（含自动下载的源视频）
        cleanup_temp_frames()

    # 3. 写入知识库（md 保留，不删除；auto 下载的源视频已随目录清理）
    save_tactics_to_kb(os.path.basename(video_path), tactics)
    print("\n视频学习完成！战术已存入 knowledge_md/，临时帧/源视频已全部清理。")


if __name__ == "__main__":
    main()
