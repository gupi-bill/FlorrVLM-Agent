#!/usr/bin/env python3
"""
FlorrVLM-Agent 轻量知识库维护 kb_maintainer.py
==============================================
v1.0 —— 知识库体积有上限，不无限膨胀撑爆小硬盘。

两个动作（都可单独运行）：
  1. 体积上限归档：整个 knowledge_md/ 超过上限(MB)时，
     把最早的笔记移到 knowledge_archive/ 归档，保证活跃库受控。
  2. 陈旧/重复笔记压缩：把高度相似的 video_tactic_*.md 合并成一个，
     去掉无信息量的重复行，减小体积。

用法:
  python kb_maintainer.py            # 一并执行 压缩+归档
  python kb_maintainer.py --report   # 只打印体积/数量，不做改动
被 agent_main 在启动自检后调用一次 run()。
"""
import argparse
import difflib
import os
import shutil
import time

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _paths():
    kb_rel = config.get("paths.knowledge_md", "knowledge_md")
    arch_rel = config.get("agent.kb_archive_dir", "knowledge_archive")
    kb = os.path.join(BASE_DIR, kb_rel)
    arch = os.path.join(BASE_DIR, arch_rel)
    return kb, arch


def _dir_size_mb(path: str) -> float:
    total = 0
    for root, _, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total / (1024 * 1024)


def _iter_md_files(kb: str, prefix: str = ""):
    if not os.path.isdir(kb):
        return
    for fn in sorted(os.listdir(kb)):
        if fn.endswith(".md") and fn.startswith(prefix) and os.path.isfile(os.path.join(kb, fn)):
            yield fn


def compress_duplicates(kb: str, ratio: float = 0.9) -> int:
    """把两两相似度 >= ratio 的 video_tactic_*.md 合并（保留信息更多的一份）。"""
    files = list(_iter_md_files(kb, "video_tactic_"))
    removed = 0
    i = 0
    while i < len(files):
        a = files[i]
        pa = os.path.join(kb, a)
        try:
            ta = open(pa, "r", encoding="utf-8").read()
        except OSError:
            i += 1
            continue
        j = i + 1
        while j < len(files):
            b = files[j]
            pb = os.path.join(kb, b)
            try:
                tb = open(pb, "r", encoding="utf-8").read()
            except OSError:
                j += 1
                continue
            if ((len(ta) >= 5 and difflib.SequenceMatcher(None, ta, tb).ratio() >= ratio)
                    or (len(ta) < 5 or len(tb) < 5)):
                # 保留更长的一份，删另一份
                keep, drop = (pa, pb) if len(ta) >= len(tb) else (pb, pa)
                try:
                    os.remove(drop)
                    removed += 1
                except OSError:
                    pass
                files.pop(j)
                continue
            j += 1
        i += 1
    return removed


def archive_oldest(kb: str, arch: str, max_mb: float) -> int:
    """活跃库超上限时，把最旧的笔记移到归档目录。返回归档文件数。"""
    os.makedirs(arch, exist_ok=True)
    moved = 0
    while _dir_size_mb(kb) > max_mb:
        files = list(_iter_md_files(kb))
        if not files:
            break
        # 按修改时间取最旧的一个移动
        oldest = min(files, key=lambda f: os.path.getmtime(os.path.join(kb, f)))
        src = os.path.join(kb, oldest)
        dst = os.path.join(arch, oldest)
        try:
            shutil.move(src, dst)
            moved += 1
        except OSError:
            break
    return moved


def run(max_mb: float = None, do_compress: bool = True, report: bool = False) -> str:
    kb, arch = _paths()
    max_mb = max_mb or config.get("agent.kb_max_mb", 50.0)
    size = _dir_size_mb(kb)
    n_files = len(list(_iter_md_files(kb)))
    if report:
        return (f"知识库: {n_files} 个笔记, {size:.1f} MB, 上限 {max_mb:.0f} MB"
                + (f"（超限，需归档）" if size > max_mb else ""))
    lines = []
    if do_compress:
        removed = compress_duplicates(kb)
        if removed:
            lines.append(f"[知识库] 合并重复笔记 {removed} 份")
    moved = archive_oldest(kb, arch, max_mb)
    if moved:
        lines.append(f"[知识库] 归档最早笔记 {moved} 份到 {os.path.basename(arch)}/")
    newsize = _dir_size_mb(kb)
    lines.append(f"[知识库] 体积 {size:.1f}→{newsize:.1f} MB（上限 {max_mb:.0f}），文件 {n_files} 个")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="只打印统计，不做改动")
    args = ap.parse_args()
    print(run(report=args.report))