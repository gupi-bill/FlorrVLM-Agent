#!/usr/bin/env python3
"""
FlorrVLM-Agent Skill 管理器 skill_manager.py
=============================================
v0.8 —— 引入"技能包(Skill)"：像普通 Agent 一样按需装配能力。

Skill 目录结构（skills/<name>/SKILL.md）：
  # <技能名>
  description: 一句话说明这个技能干什么
  entry: 技能入口函数名（expose() 返回该函数引用）
  
  下面是技能的说明文字，可包含用法示例。

本管理器功能：
- scan(): 扫描 skills/ 目录，发现所有技能的元信息
- load(name)/unload(name): 加载/卸载某个技能
- loaded(): 已加载技能列表
- call(name, *args, **kw): 调用某技能入口
- summary(): 输出能力清单文案（供 capabilities / LLM 注入）
"""
import importlib.util
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(BASE_DIR, "skills")


def _parse_meta(text: str) -> dict:
    """从 SKILL.md 头部解析 description / entry 字段。"""
    meta = {}
    for key in ("description", "entry"):
        m = re.search(rf"^{key}:\s*(.+)$", text, flags=re.MULTILINE)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def scan() -> list:
    """扫描 skills/ 下所有技能，返回元信息列表。"""
    out = []
    if not os.path.isdir(SKILLS_DIR):
        return out
    for name in sorted(os.listdir(SKILLS_DIR)):
        fpath = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not (os.path.isdir(os.path.join(SKILLS_DIR, name))
                and os.path.exists(fpath)):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            meta = _parse_meta(f.read())
        out.append({"name": name,
                    "description": meta.get("description", ""),
                    "entry": meta.get("entry", "")})
    return out


class SkillManager:
    """技能加载与编排。"""

    def __init__(self):
        self._loaded = {}   # name -> 入口函数

    def _find_entry(self, name: str):
        """按 SKILL.md 的 entry 字段定位 Python 入口函数。"""
        fpath = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not os.path.exists(fpath):
            return None, None
        with open(fpath, "r", encoding="utf-8") as f:
            meta = _parse_meta(f.read())
        entry_name = meta.get("entry")
        if not entry_name:
            return None, None
        # 约定入口写在同目录的 skill.py 里
        code_path = os.path.join(SKILLS_DIR, name, "skill.py")
        if not os.path.exists(code_path):
            return None, None
        spec = importlib.util.spec_from_file_location(
            f"skill_{name}", code_path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            return None, None
        fn = getattr(mod, entry_name, None)
        return fn, (mod, entry_name)

    def load(self, name: str) -> str:
        """加载一个技能。"""
        if name in self._loaded:
            return f"[skill] {name} 已加载"
        fn, _ = self._find_entry(name)
        if fn is None:
            return f"[skill] 无法加载 {name}: 缺 SKILL.md 或 skill.py 或入口函数"
        self._loaded[name] = fn
        return f"[skill] 已加载: {name}"

    def unload(self, name: str) -> str:
        """卸载一个技能。"""
        if name in self._loaded:
            del self._loaded[name]
            return f"[skill] 已卸载: {name}"
        return f"[skill] {name} 未加载"

    def loaded(self) -> list:
        """已加载技能名列表。"""
        return sorted(self._loaded)

    def call(self, name: str, *args, **kw):
        """调用某技能的入口函数。"""
        if name not in self._loaded:
            return f"[skill] {name} 未加载，先执行 load"
        try:
            return self._loaded[name](*args, **kw)
        except Exception as e:
            return f"[skill] {name} 调用失败: {e}"

    def summary(self) -> str:
        """输出能力清单文案。"""
        all_skills = scan()
        if not all_skills:
            return "Skill: 暂无(见 skills/ 目录)"
        loaded = set(self._loaded)
        lines = []
        for s in all_skills:
            mark = "✓" if s["name"] in loaded else "·"
            lines.append(f"  {mark} {s['name']}: {s['description']}")
        return "Skill(可用如下，用 load <名> 加载):\n" + "\n".join(lines)


if __name__ == "__main__":
    print("扫描到技能:", [s["name"] for s in scan()])