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
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

# cv2 改为软依赖（S2 审计 B3）：无 opencv 的头环境也必须能导入本模块。
# 真实抽帧需要 cv2；缺失时 extract_frames() 走 offline 分支返回空列表并给出明确提示。
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:  # pragma: no cover - 取决于运行环境
    cv2 = None
    CV2_AVAILABLE = False

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

# v2.0 S19：FRAME_DIR 原为写死常量，测试无法重定向，只能在真实仓库目录里造帧
# （既污染仓库又无法断言"清理干净"）。改为可覆盖，_frame_dir() 统一取用。
_FRAME_DIR_OVERRIDE = None


def set_frame_dir(path: str) -> str:
    """覆盖临时帧目录（测试 / 并发场景用）。传 None 恢复默认。"""
    global _FRAME_DIR_OVERRIDE
    _FRAME_DIR_OVERRIDE = path
    return _frame_dir()


def _frame_dir() -> str:
    return _FRAME_DIR_OVERRIDE or FRAME_DIR

VLM_PROMPT = """你正在观看 florr.io 游戏教程视频的一帧画面。
请仔细观察：玩家使用的花瓣组合、面对的怪物/BOSS、走位方式、操作意图。
提炼一条可复用的游戏战术，用一句话输出，不要多余解释。"""


# ---------------------------------------------------------------------------
# 临时文件清理（Ctrl+C 信号捕获）
# ---------------------------------------------------------------------------
def cleanup_temp_frames(quiet: bool = False) -> bool:
    """删除全部临时帧文件和目录，返回目录是否确已不存在。

    v2.0 S19：原实现无返回值，调用方无法断言「小硬盘友好」这条原则真的生效，
    只能靠人眼看日志。现返回 bool 供门禁用例直接断言。
    """
    import shutil
    d = _frame_dir()
    if os.path.exists(d):
        try:
            shutil.rmtree(d, ignore_errors=True)
            if not quiet:
                print(f"\n[清理] 已删除临时帧目录 {d}")
        except Exception as e:
            if not quiet:
                print(f"[清理] 删除失败: {e}")
    gone = not os.path.exists(d)
    if not gone and not quiet:
        print(f"[清理] 警告：临时帧目录仍存在 {d}")
    return gone


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
    """从视频中按间隔抽帧，返回帧文件路径列表。

    offline 降级：未安装 opencv（CV2_AVAILABLE=False）时不抛 ImportError，
    而是打印提示并返回空列表，保证上层调用链在头环境可继续走 dry-run。
    """
    if not CV2_AVAILABLE:
        print("[offline] 未安装 opencv（cv2），跳过抽帧：extract_frames() 返回空列表。"
              "有显卡/显示器的机器请安装 opencv-python-headless 后重试。")
        return []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"错误: 无法打开视频 {video_path}")
        sys.exit(1)

    os.makedirs(_frame_dir(), exist_ok=True)
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
            save_path = os.path.join(_frame_dir(), f"frame_{idx:06d}.jpg")
            cv2.imwrite(save_path, frame)
            frames.append(save_path)
        idx += 1
    cap.release()
    print(f"共抽取 {len(frames)} 帧")
    return frames


def _write_png(path: str, width: int, height: int, rgb: tuple) -> str:
    """用标准库写一个纯色 PNG（无 cv2 / 无 PIL 环境下的最小可用实现）。

    PNG = 签名 + IHDR + IDAT(zlib 压缩的逐行扫描) + IEND。每行前置一个 filter 字节 0。
    """
    import struct
    import zlib

    row = b"\x00" + bytes(rgb) * width
    raw = row * height

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, 6))
    png += _chunk(b"IEND", b"")
    _dir = os.path.dirname(path)
    if _dir:
        os.makedirs(_dir, exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return path


def synthesize_frames(count: int = 5, frame_dir: str = None,
                      width: int = 64, height: int = 48) -> list:
    """程序生成合成帧，替代真实抽帧（离线链路用）。

    本机约束：无 cv2、无 X server、无网络、无 YOLO，真实抽帧不可达。
    与其跳过整条学习链路，不如用可控的合成帧把「抽帧 → 解析 → 入库 → 清理」
    完整跑通 —— 每帧颜色不同，保证去重/逐帧处理逻辑能被真实检验。
    """
    d = frame_dir or _frame_dir()
    os.makedirs(d, exist_ok=True)
    frames = []
    for i in range(max(0, int(count))):
        # 每帧给一个明显不同的颜色，避免"所有帧一模一样"掩盖逐帧逻辑缺陷
        rgb = ((37 * i + 60) % 256, (91 * i + 30) % 256, (153 * i + 12) % 256)
        fp = os.path.join(d, f"frame_{i:06d}.png")
        _write_png(fp, width, height, rgb)
        frames.append(fp)
    return frames


def extract_frames_offline(count: int = 5, frame_dir: str = None) -> list:
    """离线抽帧入口：合成 N 帧，返回帧路径列表（与 extract_frames 同签名语义）。"""
    print(f"[offline] 使用合成帧替代真实抽帧（{count} 帧，不依赖 cv2 / 网络）")
    return synthesize_frames(count, frame_dir)


def image_to_base64(img_path: str) -> str:
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# v2.0 S19：VLM 环节原为写死的 requests 调用，无密钥时直接返回占位串，
# 整条学习链路在本机无法验证。改为「可注入 provider」：默认走真实 API，
# 离线/测试可注入 stub，链路本身得以被真正跑通与断言。
_VLM_PROVIDER = None


def _stub_vlm(b64_img: str) -> str:
    """内置 VLM stub：按图像内容产出结构化战术，不联网、不依赖密钥。

    只用于离线跑通链路与门禁验证；真实使用请配 VLM_API_URL / VLM_API_KEY。
    """
    if not b64_img:
        return "[stub] 空图像"
    # 用 base64 的校验和做稳定但各异的输出，保证去重逻辑可被检验
    h = sum(bytearray(b64_img[:64].encode("utf-8", "ignore"))) % 5
    table = [
        "低血量时立即撤退，不要恋战",
        "与高威胁目标保持距离，等其转移后再回场",
        "优先集火低威胁目标，保持场面干净",
        "组队时保护队友输出位，收益高于个人击杀数",
        "换上追击套前先确认周围没有其他威胁",
    ]
    return table[h]


def set_vlm_provider(fn) -> None:
    """注入 VLM 实现 ``fn(b64_img) -> str``；传 None 恢复默认（真实 API）。"""
    global _VLM_PROVIDER
    _VLM_PROVIDER = fn


def _default_vlm(b64_img: str) -> str:
    """默认 VLM：真实 HTTP 调用。"""
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


def vlm_extract_tactic(b64_img: str, provider=None) -> str:
    """从单帧画面提取战术文本。

    provider 非空时优先使用（离线 stub / 测试注入），否则走默认真实 API。
    """
    fn = provider or _VLM_PROVIDER
    if fn is not None:
        try:
            return fn(b64_img)
        except Exception as e:
            return f"[VLM provider 调用失败: {e}]"
    return _default_vlm(b64_img)


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


def _kb_target_dir(game_name: str = None) -> str:
    """战术入库目录。

    v2.0 S19（缺陷修复）：原先一律写 ``knowledge_md/`` 根目录，而 S15/S18 之后
    主循环检索的是 ``knowledge_md/<game>/`` —— 视频学到的战术**永远检索不到**，
    "学 → 检索"这一段实际是断的。现按激活游戏分区，与 knowledge_loop 口径一致。
    """
    if game_name:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(game_name)).strip("_")
        if safe:
            return os.path.join(KB_DIR, safe)
    try:
        import config
        game = config.active_game()
    except Exception:
        game = ""
    return os.path.join(KB_DIR, game) if game else KB_DIR


def _dedup_new(tactics: list, ratio_threshold: float = 0.75, kb_dir: str = None) -> list:
    """
    v0.4 知识库去重：把与历史 video_tactic_*.md 里已有战术过于相似的新条目剔除，
    只保留真正的新战术，避免知识库膨胀。

    kb_dir：在哪个目录范围内比对历史（默认同入库目录，保证分区内去重）。
    """
    base = kb_dir or KB_DIR
    known = []
    if os.path.isdir(base):
        for f in os.listdir(base):
            if not (f.startswith("video_tactic_") and f.endswith(".md")):
                continue
            try:
                with open(os.path.join(base, f), "r", encoding="utf-8") as fh:
                    known.append(fh.read())
            except Exception:
                continue
    known_blob = "\n".join(known)

    # v2.0 S19：原实现把「单条战术」与「整个历史文件 blob」直接比对 —— 两者长度差
    # 一个数量级，SequenceMatcher 的 ratio 天然偏低（实测 0.1~0.3），阈值 0.75 永远
    # 触发不了，去重形同虚设。改为与**逐条历史战术**比对取最大相似度。
    known_tactics = []
    for line in known_blob.splitlines():
        line = line.strip()
        if not line:
            continue
        for prefix in ("- ", "* "):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
        # "1. xxx" 形式的编号列表项
        if ". " in line[:5] and line[0].isdigit():
            line = line.split(". ", 1)[1].strip()
        if line and not line.startswith(("#", ">", "!")):
            known_tactics.append(line)

    # 剔除无意义的占位/失败提示。阈值原为 len>4，中文战术（如"别恋战"）会被误杀。
    def _useful(t):
        t = (t or "").strip()
        return len(t) >= 2 and not t.startswith("[") and not t.startswith("（")

    out = []
    for t in tactics:
        if not _useful(t):
            continue
        t_norm = t.strip()
        if any(difflib.SequenceMatcher(None, t_norm, k).ratio() >= ratio_threshold
               for k in known_tactics):
            continue  # 与已有知识太像，跳过
        out.append(t)
    return out


def save_tactics_to_kb(video_name: str, tactics: list, game_name: str = None) -> str:
    """把提取到的全部战术写成一个 Markdown 文件存入知识库（含去重、按游戏分区）。

    返回落盘文件的绝对路径（原先返回文件名，调用方拿不到路径，无法断言）。
    """
    target = _kb_target_dir(game_name)
    os.makedirs(target, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"video_tactic_{os.path.splitext(video_name)[0]}_{timestamp}.md"
    filepath = os.path.join(target, filename)

    kept = _dedup_new(tactics, kb_dir=target)
    content = f"# 视频学习战术 — {video_name}\n\n"
    content += f"> 学习时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    content += f"> 提取帧数: {len(tactics)}，去重后 {len(kept)} 条\n\n"
    content += "## 战术列表\n\n"
    for i, t in enumerate(kept, 1):
        content += f"{i}. {t}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n已保存 {len(kept)} 条新战术到知识库: {os.path.relpath(filepath, KB_DIR)}")
    return filepath


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def learn_from_video(video_path: str = None, game: str = None,
                     frame_count: int = 5, skip: int = 25,
                     vlm_provider=None, cleanup: bool = True) -> dict:
    """一次完整学习：抽帧 → 逐帧解析 → 入库 → 清理临时帧。

    返回结构化结果，便于门禁断言（原 main() 全是 print，无法验证）：
    ``{"frames", "tactics", "kept", "kb_file", "cleaned", "residual"}``。

    - 有真实视频且装了 cv2 → 走真实抽帧；否则自动降级为合成帧（离线可用）。
    - ``vlm_provider`` 可注入 stub，无密钥环境下也能产出结构化战术。
    - ``cleanup=True`` 时无论成功失败都清理临时帧目录（小硬盘友好原则）。
    """
    d = _frame_dir()
    os.makedirs(d, exist_ok=True)

    if video_path and os.path.exists(video_path) and CV2_AVAILABLE:
        frames = extract_frames(video_path, skip=skip)
        source = "video"
    else:
        frames = extract_frames_offline(frame_count, d)
        source = "synthetic"

    tactics = []
    try:
        for i, fp in enumerate(frames, 1):
            tactics.append(vlm_extract_tactic(image_to_base64(fp),
                                              provider=vlm_provider))
            # 处理完立刻删除该帧，避免大视频把磁盘撑满
            try:
                os.remove(fp)
            except OSError:
                pass
    finally:
        cleaned = cleanup_temp_frames(quiet=True) if cleanup else (not os.path.exists(d))

    kb_file = save_tactics_to_kb(
        os.path.basename(video_path) if video_path else f"synthetic_{frame_count}frames",
        tactics, game_name=game)

    residual = []
    if os.path.isdir(d):
        residual = [os.path.join(dp, f) for dp, _dn, fn in os.walk(d) for f in fn]

    with open(kb_file, "r", encoding="utf-8") as f:
        body = f.read()
    kept = body.count("\n1. ")  # 粗略：以列表首项数量代表保留条数
    if "去重后" in body:
        try:
            kept = int(body.split("去重后 ")[1].split(" ")[0])
        except Exception:
            pass

    return {
        "source": source,
        "frames": len(frames),
        "tactics": tactics,
        "kept": kept,
        "kb_file": kb_file,
        "cleaned": cleaned,
        "residual": residual,
        "game": game or "",
    }


def main():
    parser = argparse.ArgumentParser(description="FlorrVLM-Agent 视频战术学习")
    parser.add_argument("video", nargs="?", default=None,
                        help="本地教程视频文件路径 (mp4)")
    parser.add_argument("--auto", action="store_true",
                        help="自动搜索并下载教程视频（需 yt-dlp）")
    parser.add_argument("--query", default="", help="自动搜索用的查询词")
    parser.add_argument("--skip", type=int, default=25, help="抽帧间隔，默认 25")
    parser.add_argument("--synthetic", type=int, default=0,
                        help="离线模式：用 N 张合成帧跑通全链路（不依赖 cv2/网络），S19")
    parser.add_argument("--game", default="", help="战术入库到哪款游戏的知识分区，S19")
    parser.add_argument("--keep-frames", action="store_true",
                        help="保留临时帧（调试用，默认清理）")
    args = parser.parse_args()

    # S19 离线模式：无 cv2 / 无网络 / 无 VLM 密钥时，用合成帧 + 内置 stub 跑通全链路
    if args.synthetic:
        print(f"[离线] 合成帧 {args.synthetic} 张，VLM 走内置 stub，"
              f"入库分区: {args.game or '（激活游戏）'}")
        res = learn_from_video(game=args.game or None,
                               frame_count=args.synthetic,
                               vlm_provider=_stub_vlm,
                               cleanup=not args.keep_frames)
        print(f"[离线] 抽帧 {res['frames']} 张 → 解析 {len(res['tactics'])} 条 "
              f"→ 入库 {res['kept']} 条 → 清理 {'成功' if res['cleaned'] else '失败'}"
              f"（残留 {len(res['residual'])} 个文件）")
        print(f"[离线] 知识文件: {res['kb_file']}")
        return 0 if res["cleaned"] and not res["residual"] else 1

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
    sys.exit(main() or 0)
