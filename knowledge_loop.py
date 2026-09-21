"""知识闭环（S18）：学 → 检索 → 决策 → 复盘 → 回写。

本模块把"越打越强"从文档措辞变成可复现、可量化的闭环，由四部分组成：

1. ``seed_knowledge(game)``  —— 按游戏档案生成 seed 知识（学），落在
   ``knowledge_md/<game>/`` 下，保证检索能命中本游戏而非根目录旧模板。
2. ``retrieve(game, keyword)`` —— 检索并**同步记账**（检索次数 / 命中次数）。
3. ``extract_tactics`` / ``apply_tactics`` —— 把命中的条目翻译成**决策可用的规则**，
   使无 LLM 的兜底路径也能被知识影响（此前兜底完全忽略 kb_tactics，闭环断开）。
4. ``LearningStats`` + ``save/query_stats`` —— 结构化指标，持久化到
   ``run_logs/learning_stats.json``，可按游戏查询命中率 / 引用率。

设计约束（本机环境）：无网络、无 LLM/VLM 密钥，因此本模块全部为**纯本地文件与
内存操作**，不依赖任何外部服务；检索只走文本匹配，不引入 chromadb 等重依赖。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime

import yaml

import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(BASE_DIR, config.get("paths.knowledge_md", "knowledge_md"))
RUN_LOG_DIR = os.path.join(BASE_DIR, config.get("paths.run_logs", "run_logs"))
STATS_PATH = os.path.join(RUN_LOG_DIR, "learning_stats.json")

# 检索"未命中"的判定词（与 mcp_server._text_search 的返回口径保持一致）
MISS_TOKENS = ("未找到", "没有找到", "无相关", "未找到相关内容")

# 决策规则：命中知识 → 动作倾向。键是规则名，值是触发词。
TACTIC_RULES = {
    "retreat": ("撤退", "避战", "不要恋战", "低血量"),
    "keep_distance": ("保持距离", "拉开距离", "远离", "安全距离"),
    "focus_fire": ("集火", "优先攻击", "优先击杀", "优先集火", "主动"),
    "protect_ally": ("保护队友", "队友", "team"),
}

_LOCK = threading.Lock()
_STATS: dict = {}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def _safe_name(name: str) -> str:
    """把任意游戏名清洗成合法目录名（空/非法一律落到 default）。"""
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", str(name or "")).strip("_")
    return s or "default"


def game_dir(game: str = None) -> str:
    """该游戏的知识目录 ``knowledge_md/<game>/``。"""
    return os.path.join(KB_DIR, _safe_name(game or config.active_game()))


def _load_profile(game: str) -> dict:
    """读取游戏档案（缺文件/解析失败一律返回空 dict，不抛异常）。"""
    path = os.path.join(config.PROFILE_DIR, f"{_safe_name(game)}.yaml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# 1. 学：seed 知识生成
# ---------------------------------------------------------------------------
def build_seed_docs(game: str = None) -> dict:
    """按游戏档案生成 seed 文档内容 ``{文件名(不含扩展名): markdown}``。

    至少产出 ``tactics``（含"战术"关键词）与 ``boss_guide``（含 boss 关键词），
    与 agent_main 主循环的两类检索词（"战术" / "boss"）对齐。
    """
    game = game or config.active_game()
    prof = _load_profile(game)
    combat = (prof.get("combat") or {}) if isinstance(prof, dict) else {}
    pred = (prof.get("predictor") or {}) if isinstance(prof, dict) else {}
    desc = ""
    if isinstance(prof.get("game"), dict):
        desc = (prof["game"].get("description") or "").strip()

    tactics = [str(t) for t in (combat.get("tactics") or []) if str(t).strip()]
    if not tactics:
        tactics = [
            "血量不足且附近存在高威胁实体时立即撤退，不要恋战",
            "与高威胁实体保持距离，等其转移后再回场",
            "低威胁目标主动集火清理，保持场面干净",
        ]
    lines = "\n".join(f"- 战术: {t}" for t in tactics)

    # 最高威胁实体：highest_boss 档优先，其次 boss 档
    top = []
    for key in ("rarity_highest_boss", "rarity_boss", "rarity_elite"):
        vals = pred.get(key) or []
        if isinstance(vals, str):
            vals = [vals]
        top = [str(v) for v in vals if str(v).strip()]
        if top:
            break
    top_txt = "、".join(top) if top else "未声明（档案 predictor 段缺失）"

    tactics_md = (
        f"# {game} 战术知识（seed）\n\n"
        f"{desc}\n\n"
        "## 战术条目\n"
        f"{lines}\n\n"
        "## 使用说明\n"
        "- 本文件由 knowledge_loop.seed_knowledge 依据游戏档案 combat.tactics 生成\n"
        "- 决策前检索「战术」应命中本文件，命中条目会进入兜底决策规则\n"
    )

    boss_md = (
        f"# {game} 高威胁目标指南（seed）\n\n"
        f"## 最高威胁实体（boss 档）\n- {top_txt}\n\n"
        "## 应对原则\n"
        "- 最高威胁目标出现时优先判断打/跑；血量不足立即撤退并拉开距离\n"
        "- 中低威胁目标可在保持距离的前提下集火清理\n"
        "- 组队时优先保护队友输出位\n"
    )
    return {"tactics": tactics_md, "boss_guide": boss_md}


def seed_knowledge(game: str = None, force: bool = False) -> list:
    """把 seed 知识写入 ``knowledge_md/<game>/``，返回实际写入的文件路径列表。

    ``force=False``（默认）时不覆盖已存在文档，避免冲掉复盘等真实积累。
    """
    game = game or config.active_game()
    d = game_dir(game)
    os.makedirs(d, exist_ok=True)
    written = []
    for fname, content in build_seed_docs(game).items():
        fp = os.path.join(d, f"{fname}.md")
        if os.path.exists(fp) and not force:
            continue
        with open(fp, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(fp)
    return written


# ---------------------------------------------------------------------------
# 2. 检索 + 记账
# ---------------------------------------------------------------------------
def _text_search(keyword: str, search_base: str) -> str:
    """本地文本检索，输出口径与 mcp_server._text_search 一致。"""
    if not os.path.isdir(search_base):
        return "未找到相关内容"
    results = []
    kw = str(keyword or "").lower()
    for root, _dirs, files in os.walk(search_base):
        for fname in sorted(f for f in files if f.endswith(".md")):
            fp = os.path.join(root, fname)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            if kw in content.lower():
                results.append(f"## {os.path.relpath(fp, search_base)}\n{content[:2000]}")
    if not results:
        return "未找到相关内容"
    return f"共找到 {len(results)} 条结果:\n" + "\n\n---\n\n".join(results)


def is_hit(text: str) -> bool:
    """检索结果是否命中（非空且不含未命中提示）。"""
    if not text:
        return False
    low = str(text).lower()
    return not any(tok in low for tok in MISS_TOKENS)


def retrieve(game: str, keyword: str, stats: "LearningStats" = None,
             base_dir: str = None) -> tuple:
    """检索该游戏知识并记账，返回 ``(文本, 是否命中)``。"""
    base = base_dir or game_dir(game)
    text = _text_search(keyword, base)
    hit = is_hit(text)
    (stats or get_stats(game)).record_search(keyword, hit)
    return text, hit


# ---------------------------------------------------------------------------
# 3. 命中条目 → 决策规则
# ---------------------------------------------------------------------------
def extract_tactics(text: str) -> list:
    """从检索结果中抽取生效的战术规则名。"""
    if not is_hit(text):
        return []
    low = str(text).lower()
    return [name for name, words in TACTIC_RULES.items()
            if any(w in low for w in words)]


def apply_tactics(decision: str, tactics: list) -> str:
    """知识驱动的兜底决策：返回受知识影响的动作，无影响时返回空串。

    这是"命中条目真的进入决策"的落点 —— 没有它，无 LLM 时知识只进 prompt 不进动作。
    """
    if not tactics:
        return ""
    t = set(tactics)
    if decision == "retreat":
        return "defend"
    if decision == "cautious_fight":
        # 知识里有撤退/保持距离类条目时，谨慎战斗降级为防守
        if t & {"retreat", "keep_distance"}:
            return "defend"
    if decision == "fight":
        if t & {"focus_fire", "protect_ally"}:
            return "attack"
    return ""


def decide_with_knowledge(decision: str, kb_text: str, stats: "LearningStats" = None,
                          keyword: str = "", game: str = None) -> tuple:
    """``(动作, 是否引用了知识)``：命中且产生规则才算一次有效引用。"""
    tactics = extract_tactics(kb_text)
    action = apply_tactics(decision, tactics)
    cited = bool(action) and bool(tactics)
    if cited and stats is not None:
        stats.record_citation(keyword or "-")
    return action, cited


# ---------------------------------------------------------------------------
# 4. 指标：LearningStats
# ---------------------------------------------------------------------------
class LearningStats:
    """检索 / 命中 / 引用三计数器，支持按关键词下钻与持久化。"""

    def __init__(self, game: str = "", searches: int = 0, hits: int = 0,
                 citations: int = 0, by_keyword: dict = None, updated_at: str = ""):
        self.game = game or ""
        self.searches = int(searches)
        self.hits = int(hits)
        self.citations = int(citations)
        self.by_keyword = {k: list(v) for k, v in (by_keyword or {}).items()}
        self.updated_at = updated_at or ""

    # -- 记账 -------------------------------------------------------------
    def record_search(self, keyword: str, hit: bool) -> None:
        hit = bool(hit)
        self.searches += 1
        self.hits += int(hit)
        col = self._col(keyword)
        col[0] += 1
        col[1] += int(hit)
        self._touch()

    def record_citation(self, keyword: str = "-") -> None:
        self.citations += 1
        self._col(keyword)[2] += 1
        self._touch()

    def _col(self, keyword: str) -> list:
        """关键词下钻列 ``[检索, 命中, 引用]``。"""
        return self.by_keyword.setdefault(str(keyword or "-"), [0, 0, 0])

    def _touch(self) -> None:
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # -- 指标 -------------------------------------------------------------
    @property
    def hit_rate(self) -> float:
        return round(self.hits / self.searches, 4) if self.searches else 0.0

    @property
    def citation_rate(self) -> float:
        return round(self.citations / self.hits, 4) if self.hits else 0.0

    def to_dict(self) -> dict:
        return {
            "game": self.game,
            "searches": self.searches,
            "hits": self.hits,
            "citations": self.citations,
            "hit_rate": self.hit_rate,
            "citation_rate": self.citation_rate,
            "by_keyword": {k: list(v) for k, v in self.by_keyword.items()},
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LearningStats":
        d = d or {}
        return cls(
            game=d.get("game", ""),
            searches=d.get("searches", 0),
            hits=d.get("hits", 0),
            citations=d.get("citations", 0),
            by_keyword=d.get("by_keyword") or {},
            updated_at=d.get("updated_at", ""),
        )

    def __repr__(self):  # pragma: no cover - 调试用
        return (f"<LearningStats {self.game} s={self.searches} h={self.hits} "
                f"c={self.citations} hit={self.hit_rate} cit={self.citation_rate}>")


# ---------------------------------------------------------------------------
# 注册表与持久化
# ---------------------------------------------------------------------------
def get_stats(game: str = None) -> LearningStats:
    """取（或建）该游戏的进程内计数器。"""
    g = _safe_name(game or config.active_game())
    with _LOCK:
        if g not in _STATS:
            _STATS[g] = LearningStats(game=g)
        return _STATS[g]


def reset_stats(game: str = None) -> None:
    """清空计数器（None = 全部）。测试用。"""
    with _LOCK:
        if game is None:
            _STATS.clear()
        else:
            _STATS.pop(_safe_name(game), None)


def save(path: str = None) -> str:
    """把全部游戏计数落盘为 JSON，返回路径。"""
    p = path or STATS_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with _LOCK:
        payload = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "games": {g: s.to_dict() for g, s in _STATS.items()},
        }
    tmp = f"{p}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    return p


def read_stats(path: str = None) -> dict:
    """读盘（文件不存在返回空结构）。"""
    p = path or STATS_PATH
    if not os.path.exists(p):
        return {"updated_at": "", "games": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"updated_at": "", "games": {}}
    if not isinstance(data, dict):
        return {"updated_at": "", "games": {}}
    data.setdefault("games", {})
    return data


def query_stats(game: str = None, path: str = None) -> dict:
    """查询指标：``game=None`` 时额外给出 overall 聚合。

    优先返回进程内实时值（未落盘也算），盘上其它游戏一并合并。
    """
    data = read_stats(path)
    games = {}
    for g, d in (data.get("games") or {}).items():
        st = LearningStats.from_dict(d)
        games[g] = st
    with _LOCK:
        for g, st in _STATS.items():
            # 进程内计数覆盖盘上同名词条（实时优先）
            games[g] = LearningStats(
                game=g, searches=st.searches, hits=st.hits, citations=st.citations,
                by_keyword=st.by_keyword, updated_at=st.updated_at)

    if game:
        st = games.get(_safe_name(game))
        return st.to_dict() if st else {
            "game": game, "searches": 0, "hits": 0, "citations": 0,
            "hit_rate": 0.0, "citation_rate": 0.0, "by_keyword": {}, "updated_at": ""}

    total = LearningStats(game="__all__")
    for st in games.values():
        total.searches += st.searches
        total.hits += st.hits
        total.citations += st.citations
        for k, col in st.by_keyword.items():
            dst = total.by_keyword.setdefault(k, [0, 0, 0])
            for i in range(3):
                dst[i] += col[i]
    return {
        "games": {g: s.to_dict() for g, s in games.items()},
        "overall": {
            "games": len(games),
            "searches": total.searches,
            "hits": total.hits,
            "citations": total.citations,
            "hit_rate": total.hit_rate,
            "citation_rate": total.citation_rate,
        },
        "updated_at": data.get("updated_at", ""),
    }


def stats_summary(game: str = None) -> str:
    """人类可读的一行摘要（给 CLI / 日志用）。"""
    q = query_stats(game)
    if game:
        return (f"[{game}] 检索 {q['searches']} 次 / 命中 {q['hits']} 次 "
                f"(命中率 {q['hit_rate']:.0%}) / 引用 {q['citations']} 次 "
                f"(引用率 {q['citation_rate']:.0%})")
    ov = q["overall"]
    return (f"[全部 {ov['games']} 款游戏] 检索 {ov['searches']} 次 / 命中 {ov['hits']} 次 "
            f"(命中率 {ov['hit_rate']:.0%}) / 引用 {ov['citations']} 次 "
            f"(引用率 {ov['citation_rate']:.0%})")
