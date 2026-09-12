#!/usr/bin/env python3
"""
vlm_detect.py — VLM 版单图检测入口
=====================================
直接调 VLM API 看截图，输出结构化 JSON。
不需要 YOLO 模型权重，低配置机器也能跑。

用法: python vlm_detect.py --image /tmp/florr_frame.png
输出: 纯 JSON 到 stdout
"""
import argparse
import base64
import io
import json
import os

import requests
from PIL import Image

API_URL = (os.getenv("VLM_API_URL", "") or "").replace("/chat/completions", "") + "/chat/completions"
API_KEY = os.getenv("VLM_API_KEY", "")
MODEL = os.getenv("VLM_MODEL", "agnes-2.5-flash")

PROMPT = """你是 florr.io 游戏视觉识别器。看这张游戏截图，输出 JSON：

{
  "player": {"alive": true, "hp": 100, "max_hp": 100, "x": 960, "y": 540, "power_score": 100},
  "entities": [
    {"raw_id": "怪物英文名", "rarity": "Common|Unusual|Rare|Epic|Legendary|Mythic|Ultra|Super|Unique|Eternal", "x": 像素x, "y": 像素y}
  ],
  "afk_popup": false
}

规则：
- 坐标是屏幕像素（1920x1080），玩家在画面中心附近。
- 只识别真正在画面上的怪物，最多 15 个。
- rarity 按颜色/大小判断：小白点=Common，蓝=Rare，紫=Epic，金=Legendary，红/大黑=Mythic+，超大BOSS=Super及以上。
- 如果是加载/连接/主菜单界面，player.alive=false，entities=[]。
- 只输出 JSON，不要解释。
"""


def detect(image_path: str) -> dict:
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((960, 540))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=65)
    b64 = base64.b64encode(buf.getvalue()).decode()

    r = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]}],
            "max_tokens": 500,
            "temperature": 0.1,
        },
        timeout=25,
        proxies={"http": None, "https": None},
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    if "```" in content:
        content = content.split("```")[1].split("```")[0]
        if content.startswith("json"):
            content = content[4:]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"player": {"alive": True, "hp": 100}, "entities": [], "afk_popup": False, "_parse_error": content[:200]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    args = ap.parse_args()
    print(json.dumps(detect(args.image), ensure_ascii=False))
