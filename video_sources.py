#!/usr/bin/env python3
"""
FlorrVLM-Agent 视频来源注册表 video_sources.py
=================================================
v0.4：教程视频"自动找 → 学 → 用完即删"闭环里"自动找"的部分。

用"注册表"组织来源，不写死单一平台：
- 每个来源是一个 {name, enabled, fetch} 条目，可增删
- 底层用通用下载器 yt-dlp，天然支持 YouTube / B站 / 抖音等几十个站点
- 换游戏/换平台时增删条目即可，不碰其它代码（为 v3.0 通用化留接口）
- 来源单独开关：环境变量 VIDEO_SOURCE_<NAME>=0/1（缺省启用）
"""
import os
import shutil
import subprocess

USE_YTDLP = shutil.which("yt-dlp") is not None


def _enabled(name: str) -> bool:
    """读取来源开关：VIDEO_SOURCE_<NAME>=0 关闭，其余缺省启用。"""
    key = f"VIDEO_SOURCE_{name.upper()}"
    val = os.getenv(key, "")
    return val != "0"


def _fetch_ytdlp(query: str, limit: int) -> list:
    """yt-dlp 通用搜索（平台支持面由 yt-dlp 决定，非本代码写死）。"""
    if not USE_YTDLP:
        return [("（可选）未安装 yt-dlp，跳过自动搜索。", "")]
    try:
        out = subprocess.run(
            ["yt-dlp", f"ytsearch{limit}:{query}",
             "--get-title", "--get-url", "--skip-download", "--no-playlist"],
            capture_output=True, text=True, timeout=60,
        )
        lines = [l for l in out.stdout.splitlines() if l.strip()]
        # 输出交替为 【标题, URL, 标题, URL,...】
        titles, urls = lines[::2], lines[1::2]
        return list(zip(titles, urls))[:limit]
    except Exception:
        return [("yt-dlp 搜索失败，可手动下载视频传入本地路径。", "")]


# ---------------------------------------------------------------------------
# 注册表：以后加 "B站专属适配" / "抖音适配" 在这里追一条即可
# ---------------------------------------------------------------------------
def SOURCES():
    return [
        {"name": "ytdlp", "enabled": _enabled("ytdlp")},
        # 预留位：{ "name": "bilibili", "enabled": _enabled("bilibili"),
        #              "fetch": _fetch_bilibili },
    ]


def search_videos(query: str, limit: int = 3) -> list:
    """
    遍历启用来源汇总视频候选。
    返回 [(标题, url), ...]；首项若带"未"字，说明当前无可用的来源。
    """
    results = []
    for src in SOURCES():
        if src["enabled"] and src["name"] == "ytdlp":
            results.extend(_fetch_ytdlp(query, limit))
    return results or [("未找到可用来源。", "")]