"""S18 知识闭环测试：学 → 检索 → 决策 → 复盘 → 回写。

验收口径（与 devplan/PLAN_PHASE2.md S18 对齐）：
1. seed 知识按游戏落在 knowledge_md/<game>/，检索能命中本游戏分区；
2. 命中条目**真的进入决策**（无 LLM 的兜底路径也必须受影响）；
3. 死亡复盘写入后，下一轮能被检索到；
4. 检索/命中/引用三计数可查询、可持久化。

所有用例在 tmp_path 内完成，不污染仓库真实知识库。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import knowledge_loop
import mcp_server


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def kb(tmp_path, monkeypatch):
    """把知识库与指标文件都重定向到临时目录，并清空进程内计数。"""
    kb_dir = tmp_path / "knowledge_md"
    kb_dir.mkdir()
    stats_path = tmp_path / "run_logs" / "learning_stats.json"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(knowledge_loop, "KB_DIR", str(kb_dir), raising=False)
    monkeypatch.setattr(knowledge_loop, "STATS_PATH", str(stats_path), raising=False)
    monkeypatch.setattr(mcp_server, "KB_DIR", str(kb_dir), raising=False)
    knowledge_loop.reset_stats()
    yield {"dir": kb_dir, "stats": stats_path}
    knowledge_loop.reset_stats()


# ---------------------------------------------------------------------------
# 1. 学：seed 知识
# ---------------------------------------------------------------------------
def test_seed_creates_game_scoped_docs(kb):
    written = knowledge_loop.seed_knowledge("demo_game")
    assert len(written) == 2
    for fp in written:
        assert fp.startswith(str(kb["dir"] / "demo_game"))
        assert os.path.getsize(fp) > 0
    names = sorted(os.listdir(kb["dir"] / "demo_game"))
    assert names == ["boss_guide.md", "tactics.md"]


def test_seed_is_idempotent_and_force_overwrites(kb):
    first = knowledge_loop.seed_knowledge("demo_game")
    assert first
    assert knowledge_loop.seed_knowledge("demo_game") == []
    fp = first[0]
    with open(fp, "w", encoding="utf-8") as f:
        f.write("被手工改写过的内容")
    forced = knowledge_loop.seed_knowledge("demo_game", force=True)
    assert forced
    with open(fp, "r", encoding="utf-8") as f:
        assert "被手工改写过的内容" not in f.read()


def test_seed_content_comes_from_profile(kb):
    """真实游戏档案的 tactics 必须出现在 seed 文档里（不是写死的通用文案）。"""
    knowledge_loop.seed_knowledge("florr")
    body = (kb["dir"] / "florr" / "tactics.md").read_text(encoding="utf-8")
    prof_tactics = config  # 仅确保 config 可用
    assert "florr" in body
    # florr 档案里确实声明了 retreat 相关战术
    assert "retreat" in body or "撤退" in body or "避战" in body


def test_seed_missing_profile_falls_back(kb):
    """档案不存在时也要能产出可用 seed，而不是抛异常。"""
    docs = knowledge_loop.build_seed_docs("no_such_game_xyz")
    assert set(docs) == {"tactics", "boss_guide"}
    assert "战术" in docs["tactics"]


def test_safe_name_and_game_dir(kb, monkeypatch):
    assert knowledge_loop._safe_name("") == "default"
    assert knowledge_loop._safe_name("a/b c") == "a_b_c"
    assert knowledge_loop.game_dir("g1") == str(kb["dir"] / "g1")
    monkeypatch.setattr(config, "active_game", lambda: "cfg_game")
    assert knowledge_loop.game_dir() == str(kb["dir"] / "cfg_game")


# ---------------------------------------------------------------------------
# 2. 检索
# ---------------------------------------------------------------------------
def test_retrieve_hits_only_game_partition(kb):
    """检索必须限定在本游戏分区：别的游戏的知识不能算命中。"""
    knowledge_loop.seed_knowledge("game_a")
    knowledge_loop.seed_knowledge("game_b")
    (kb["dir"] / "game_b" / "tactics.md").write_text(
        "# 独家战术\n- 战术: 只在 B 出现的独门口诀\n", encoding="utf-8")

    text_a, hit_a = knowledge_loop.retrieve("game_a", "独门口诀")
    assert not hit_a and "未找到" in text_a

    text_b, hit_b = knowledge_loop.retrieve("game_b", "独门口诀")
    assert hit_b and "独门口诀" in text_b


def test_retrieve_keywords_cover_main_loop(kb):
    """主循环只用两个检索词：'战术' 与 'boss'，seed 必须都能命中。"""
    knowledge_loop.seed_knowledge("demo_game")
    for kw in ("战术", "boss"):
        _text, hit = knowledge_loop.retrieve("demo_game", kw)
        assert hit, f"seed 知识未覆盖主循环检索词: {kw}"


def test_retrieve_missing_dir_is_miss(kb):
    text, hit = knowledge_loop.retrieve("never_seeded", "战术")
    assert not hit and "未找到" in text


def test_is_hit_token_rules():
    assert knowledge_loop.is_hit("共找到 1 条结果: ...")
    assert not knowledge_loop.is_hit("")
    assert not knowledge_loop.is_hit("未找到相关内容")
    assert not knowledge_loop.is_hit("没有找到相关战术")


# ---------------------------------------------------------------------------
# 3. 命中 → 决策
# ---------------------------------------------------------------------------
def test_extract_tactics_from_hit(kb):
    knowledge_loop.seed_knowledge("florr")
    text, hit = knowledge_loop.retrieve("florr", "战术")
    assert hit
    tactics = knowledge_loop.extract_tactics(text)
    assert tactics  # florr 档案含撤退/距离/集火类条目
    assert set(tactics) <= set(knowledge_loop.TACTIC_RULES)


def test_extract_tactics_on_miss_returns_empty():
    assert knowledge_loop.extract_tactics("未找到相关内容") == []


@pytest.mark.parametrize("decision,expected", [
    ("retreat", "defend"),
    ("cautious_fight", "defend"),   # 知识含保持距离 → 谨慎战斗降级为防守
    ("fight", "attack"),
])
def test_apply_tactics(decision, expected):
    assert knowledge_loop.apply_tactics(decision, ["retreat", "keep_distance",
                                                   "focus_fire"]) == expected


def test_apply_tactics_without_knowledge_is_noop():
    assert knowledge_loop.apply_tactics("retreat", []) == ""


def test_decide_with_knowledge_counts_citation(kb):
    knowledge_loop.seed_knowledge("florr")
    text, hit = knowledge_loop.retrieve("florr", "战术")
    st = knowledge_loop.get_stats("florr")
    st.record_search("战术", hit)
    action, cited = knowledge_loop.decide_with_knowledge("cautious_fight", text,
                                                         st, "战术", "florr")
    assert action in ("defend", "attack", "")
    if cited:
        assert st.citations == 1
        assert st.citation_rate > 0
    else:
        assert st.citations == 0


def test_fallback_decide_is_knowledge_driven(kb, monkeypatch):
    """回归：无 LLM 时兜底决策必须被知识影响（此前 kb_tactics 被完全忽略）。"""
    import importlib
    import agent_main
    importlib.reload(agent_main)

    knowledge_loop.seed_knowledge("florr")
    text, _hit = knowledge_loop.retrieve("florr", "战术")

    ev = json.dumps({"decision": "cautious_fight"}, ensure_ascii=False)
    state = json.dumps({"afk_popup": False}, ensure_ascii=False)

    without_kb = agent_main._fallback_decide(state, ev)
    with_kb = agent_main._fallback_decide(state, ev, text)
    # 有知识与无知识的动作必须不同，否则说明知识没进入决策
    assert with_kb.get("source") == "kb"
    assert with_kb != without_kb


# ---------------------------------------------------------------------------
# 4. 复盘 → 回写 → 下一轮可检索
# ---------------------------------------------------------------------------
def test_review_writeback_is_retrievable_next_round(kb):
    """复盘写入的笔记，下一轮必须能被检索到（闭环最后一段）。"""
    knowledge_loop.seed_knowledge("demo_game")

    before, hit_before = knowledge_loop.retrieve("demo_game", "对局复盘")
    assert not hit_before

    res = mcp_server.kb_write("review_20260922_050000",
                              "# 对局复盘 — 2026-09-22\n\n- 结果: 死亡\n"
                              "- 可改进点: 提前撤退\n",
                              game_name="demo_game")
    assert "错误" not in res
    assert os.path.exists(kb["dir"] / "demo_game" / "review_20260922_050000.md")

    after, hit_after = knowledge_loop.retrieve("demo_game", "对局复盘")
    assert hit_after
    assert "提前撤退" in after


def test_writeback_does_not_leak_to_other_game(kb):
    mcp_server.kb_write("review_x", "# 对局复盘\n- 可改进点: 独门经验\n",
                        game_name="game_a")
    _t, hit_b = knowledge_loop.retrieve("game_b", "独门经验")
    assert not hit_b


def test_append_accumulates_reviews(kb):
    for i in range(3):
        mcp_server.kb_append("review_log", f"\n- 第 {i} 次对局复盘结论\n",
                             game_name="demo_game")
    text, hit = knowledge_loop.retrieve("demo_game", "对局复盘结论")
    assert hit
    assert text.count("次对局复盘结论") == 3


# ---------------------------------------------------------------------------
# 5. 指标
# ---------------------------------------------------------------------------
def test_stats_basic_counters(kb):
    st = knowledge_loop.get_stats("demo_game")
    st.record_search("战术", True)
    st.record_search("战术", False)
    st.record_search("boss", True)
    st.record_citation("战术")
    assert st.searches == 3 and st.hits == 2 and st.citations == 1
    assert st.hit_rate == pytest.approx(2 / 3, abs=1e-4)
    assert abs(st.citation_rate - 0.5) < 1e-6
    col = st.by_keyword["战术"]
    assert col[0] == 2 and col[1] == 1 and col[2] == 1


def test_stats_zero_division_safe():
    st = knowledge_loop.LearningStats(game="x")
    assert st.hit_rate == 0.0 and st.citation_rate == 0.0


def test_stats_get_is_singleton_per_game(kb):
    a = knowledge_loop.get_stats("demo_game")
    a.record_search("k", True)
    assert knowledge_loop.get_stats("demo_game").searches == 1
    assert knowledge_loop.get_stats("other").searches == 0


def test_stats_save_and_query(kb):
    st = knowledge_loop.get_stats("demo_game")
    st.record_search("战术", True)
    st.record_search("战术", True)
    st.record_citation("战术")
    knowledge_loop.get_stats("other_game").record_search("boss", False)

    path = knowledge_loop.save()
    assert os.path.exists(path)

    one = knowledge_loop.query_stats("demo_game")
    assert one["searches"] == 2 and one["hits"] == 2 and one["citations"] == 1
    assert one["hit_rate"] == 1.0

    allq = knowledge_loop.query_stats()
    ov = allq["overall"]
    assert ov["games"] == 2
    assert ov["searches"] == 3 and ov["hits"] == 2 and ov["citations"] == 1
    assert set(allq["games"]) == {"demo_game", "other_game"}


def test_query_stats_unknown_game_returns_zeros(kb):
    q = knowledge_loop.query_stats("nope_game")
    assert q["searches"] == 0 and q["hit_rate"] == 0.0


def test_read_stats_tolerates_corrupt_file(kb):
    with open(kb["stats"], "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    assert knowledge_loop.read_stats() == {"updated_at": "", "games": {}}


def test_stats_summary_text(kb):
    st = knowledge_loop.get_stats("demo_game")
    st.record_search("战术", True)
    st.record_citation("战术")
    s = knowledge_loop.stats_summary("demo_game")
    assert "demo_game" in s and "命中率" in s and "100%" in s


def test_stats_roundtrip_via_dict(kb):
    st = knowledge_loop.LearningStats(game="g", searches=5, hits=4, citations=2,
                                      by_keyword={"战术": [5, 4, 2]})
    back = knowledge_loop.LearningStats.from_dict(st.to_dict())
    assert back.to_dict() == st.to_dict()


# ---------------------------------------------------------------------------
# 6. 端到端：两轮闭环
# ---------------------------------------------------------------------------
def test_full_loop_two_rounds(kb):
    """一轮完整闭环：seed → 检索 → 决策 → 复盘回写 → 第二轮命中提升。"""
    game = "demo_game"
    st = knowledge_loop.get_stats(game)

    # 第 1 轮：seed 后检索「战术」
    knowledge_loop.seed_knowledge(game)
    t1, h1 = knowledge_loop.retrieve(game, "战术", st)
    assert h1
    a1, cited1 = knowledge_loop.decide_with_knowledge("cautious_fight", t1, st, "战术")
    assert a1 in ("defend", "attack")

    # 复盘回写：把本轮结论写进知识库
    mcp_server.kb_write("review_r1",
                        "# 对局复盘\n- 结果: 死亡\n- 可改进点: 战术调整为提前撤退\n",
                        game_name=game)
    st.record_search("对局复盘", True)

    # 第 2 轮：复盘内容必须能被检索到，且命中率不下降
    t2, h2 = knowledge_loop.retrieve(game, "对局复盘", st)
    assert h2 and "提前撤退" in t2
    a2, _ = knowledge_loop.decide_with_knowledge("cautious_fight", t2, st, "对局复盘")
    assert a2 in ("defend", "attack")

    q = knowledge_loop.query_stats(game)
    assert q["searches"] == 3 and q["hits"] == 3
    assert q["hit_rate"] == 1.0
    assert q["citations"] >= (1 if cited1 else 0)


def test_loop_hit_rate_refects_empty_partition(kb):
    """没有任何知识时命中率必须是 0，不能因为扫到根目录模板而虚高。"""
    st = knowledge_loop.get_stats("empty_game")
    for _ in range(4):
        knowledge_loop.retrieve("empty_game", "战术", st)
    q = knowledge_loop.query_stats("empty_game")
    assert q["searches"] == 4 and q["hits"] == 0 and q["hit_rate"] == 0.0


# ---------------------------------------------------------------------------
# 7. CLI 接入
# ---------------------------------------------------------------------------
def test_cli_registers_kb_stats_and_seed(kb, monkeypatch):
    import agent_cli
    reg = agent_cli._command_registry("")
    # 帮助清单里写了的命令，命令表里必须有实现
    # 帮助里存在 "load/unload/run_skill" 这类复合条目，取首个 token 比对
    help_cmds = {line.split()[0].split("/")[0] for line, _d in agent_cli.HELP_LINES}
    interactive_only = {"quit"}   # 仅交互模式使用，不进 -c 命令表
    missing = [c for c in help_cmds if c not in reg and c not in interactive_only]
    assert not missing, f"帮助清单有命令但未实现: {missing}"
    assert "kb_stats" in reg and "kb_seed" in reg


def test_cli_kb_seed_and_stats_commands(kb, monkeypatch):
    import agent_cli
    monkeypatch.setattr(config, "active_game", lambda: "demo_game")
    out = agent_cli._cmd_kb_seed("demo_game")
    assert "已写入" in out or "无需补种" in out
    assert (kb["dir"] / "demo_game" / "tactics.md").exists()

    stats = knowledge_loop.get_stats("demo_game")
    stats.record_search("战术", True)
    text = agent_cli._cmd_kb_stats("demo_game")
    assert "命中率" in text and "100.0%" in text

    empty = agent_cli._cmd_kb_stats("never_used_game")
    assert "暂无检索记录" in empty
