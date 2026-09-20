#!/usr/bin/env python3
"""
S5 · 会话记忆 session.py 实测

覆盖：读写往返 / 旧档案兼容 / 损坏档案降级 / 续玩点 / 记账累加 /
战绩历史 & 统计 / 快照读取 / 脏数据不炸。
所有落盘路径重定向到 tmp_path，不污染仓库。
"""
import json
import os

import pytest

import config
import session


@pytest.fixture
def sess(monkeypatch, tmp_path):
    """把 session 的三个落盘路径全部重定向到临时目录。"""
    state = tmp_path / "agent_state.json"
    hist = tmp_path / "session_history.json"
    snap_dir = tmp_path / "run_logs"
    snap_dir.mkdir(exist_ok=True)
    snap = snap_dir / "agent_snapshot.json"
    monkeypatch.setattr(session, "STATE_FILE", str(state))
    monkeypatch.setattr(session, "HISTORY_FILE", str(hist))
    monkeypatch.setattr(session, "SNAP_PATH", str(snap))
    return {"state": state, "hist": hist, "snap": snap}


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


# ---------------------------------------------------------------------------
# safe_int
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expect", [
    (0, 0), (12, 12), ("7", 7), ("3.0", 3), (3.9, 3),
    (None, 0), ("", 0), ("abc", 0), ([], 0), ({}, 0),
    (float("nan"), 0), (float("inf"), 0), (True, 0),
])
def test_safe_int(raw, expect):
    assert session.safe_int(raw) == expect


def test_safe_int_default():
    assert session.safe_int("x", 5) == 5
    assert session.safe_int(None, -1) == -1


# ---------------------------------------------------------------------------
# 默认档案 / load
# ---------------------------------------------------------------------------
def test_default_shape(sess):
    d = session._default()
    for key in ("game", "status", "last_played", "last_rounds", "last_report",
                "brief", "sessions", "total_deaths", "skills_last", "resumed"):
        assert key in d
    assert d["total_deaths"] == 0 and d["sessions"] == 0


def test_load_missing_file_returns_default(sess):
    st = session.load()
    assert st["sessions"] == 0
    assert st["status"] == "idle"


def test_save_load_roundtrip(sess):
    st = session.load()
    st["game"] = "space_invaders"
    st["total_deaths"] = 3
    session.save(st)
    back = session.load()
    assert back["game"] == "space_invaders"
    assert back["total_deaths"] == 3


# v2.0 修复：旧版本档案没有 v1.4 新增字段，load 必须补齐而不是 KeyError
def test_load_backfills_new_fields(sess):
    _write(sess["state"], {"game": "florr", "status": "done"})
    st = session.load()
    assert st["sessions"] == 0
    assert st["total_deaths"] == 0
    assert st["skills_last"] == []
    assert st["resumed"] is False
    assert st["game"] == "florr"          # 旧值保留


@pytest.mark.parametrize("bad", ["not json{{", "", "   ", "[1,2,3]", '"str"', "42", "null"])
def test_load_corrupted_falls_back(sess, bad):
    with open(sess["state"], "w", encoding="utf-8") as f:
        f.write(bad)
    st = session.load()
    assert st["status"] == "idle"


# v2.0 修复：list 型档案原会 "cannot convert dictionary update sequence"
def test_load_list_payload_falls_back(sess):
    _write(sess["state"], [{"game": "x"}])
    assert session.load()["status"] == "idle"


def test_save_non_serializable_raises_runtime(sess):
    with pytest.raises(RuntimeError):
        session.save({"bad": {1, 2, 3}})


# ---------------------------------------------------------------------------
# record_start / resume_info / mark_resumed
# ---------------------------------------------------------------------------
def test_record_start_fresh_not_resumable(sess):
    assert session.record_start("florr", []) is False
    assert session.load()["resume_point"] is None
    assert session.resume_info() == ""


def test_record_start_with_history_is_resumable(sess):
    session.record_end("florr", 30, 2, ["report"])
    assert session.record_start("florr", ["report"]) is True
    rp = session.load()["resume_point"]
    assert rp["from_rounds"] == 30
    assert rp["total_deaths_so_far"] == 2
    assert rp["skills"] == ["report"]


def test_resume_info_content(sess):
    session.record_end("florr", 30, 2, ["report"])
    session.record_start("florr", ["report"])
    info = session.resume_info()
    assert "续玩" in info and "30" in info and "2" in info and "report" in info


def test_resume_info_short_form_after_mark_resumed(sess):
    session.record_end("florr", 30, 2, ["report"])
    session.record_start("florr", ["report"])
    session.mark_resumed()
    info = session.resume_info()
    assert "继续上次进度" in info and "已到回合 30" in info


# v2.0 修复：resume_point 缺 game / from_rounds 键时原会 KeyError
@pytest.mark.parametrize("rp", [
    {}, {"game": "florr"}, {"from_rounds": "x"}, {"skills": None},
])
def test_resume_info_missing_keys_safe(sess, rp):
    _write(sess["state"], {"resume_point": rp})
    assert isinstance(session.resume_info(), str)


def test_record_start_none_skills(sess):
    session.record_end("florr", 5, 0, [])
    assert session.record_start("florr", None) is True


# ---------------------------------------------------------------------------
# record_end / 历史 / 统计
# ---------------------------------------------------------------------------
def test_record_end_accumulates(sess):
    session.record_end("florr", 10, 1, ["report", "report"])
    session.record_end("florr", 20, 2, [])
    st = session.load()
    assert st["sessions"] == 2
    assert st["total_deaths"] == 3
    assert st["last_rounds"] == 20
    assert st["skills_last"] == []
    assert st["status"] == "done"
    assert st["resume_point"] is None


def test_record_end_skills_dedup_sorted(sess):
    session.record_end("florr", 1, 0, ["b", "a", "b"])
    assert session.load()["skills_last"] == ["a", "b"]


@pytest.mark.parametrize("deaths,expect", [
    (None, 0), (-5, 0), (0, 0), (3, 3), ("4", 4), ("x", 0), (2.7, 2),
])
def test_record_end_dirty_deaths(sess, deaths, expect):
    session.record_end("florr", 1, deaths, [])
    assert session.load()["total_deaths"] == expect


def test_record_end_dirty_rounds(sess):
    session.record_end("florr", "abc", 0, [])
    assert session.load()["last_rounds"] == 0


def test_history_appended_and_ordered(sess):
    for i in (1, 2, 3):
        session.record_end("florr", i * 10, i, [])
    h = session.history()
    assert len(h) == 3
    assert [r["rounds"] for r in h] == [10, 20, 30]


def test_history_trimmed_to_max(sess, monkeypatch):
    monkeypatch.setattr(config, "_CFG", dict(getattr(config, "_CFG", {}) or {}))
    monkeypatch.setattr(config, "get", lambda p, d=None: 3 if p == "session.history_max" else d)
    for i in range(6):
        session.record_end("florr", i, 0, [])
    h = session.history()
    assert len(h) == 3
    assert [r["rounds"] for r in h] == [3, 4, 5]


def test_stats_aggregate(sess):
    session.record_end("florr", 10, 1, [])
    session.record_end("florr", 30, 2, [])
    s = session.stats()
    assert s["sessions"] == 2
    assert s["total_rounds"] == 40
    assert s["total_deaths"] == 3
    assert s["avg_rounds"] == 20.0
    assert s["best_rounds"] == 30
    assert [r["rounds"] for r in s["recent"]] == [30, 10]   # 新→旧


def test_stats_empty(sess):
    s = session.stats()
    assert s["sessions"] == 0 and s["recent"] == []


# v2.0 修复：历史条目缺 at / rounds 非数字时原会 KeyError / ValueError
def test_stats_dirty_history(sess):
    _write(sess["hist"], [{"rounds": "x"}, {}, {"at": None, "rounds": 5, "deaths": None}, "junk"])
    s = session.stats()
    assert s["total_rounds"] == 5
    assert isinstance(session.stats_text(), str)


def test_history_non_list_file(sess):
    _write(sess["hist"], {"a": 1})
    assert session.history() == []


# ---------------------------------------------------------------------------
# 快照
# ---------------------------------------------------------------------------
def test_snapshot_missing_file(sess):
    assert session.snapshot_rounds_deaths() == (0, 0)


def test_snapshot_read(sess):
    _write(sess["snap"], {"round": 42, "deaths": 3})
    assert session.snapshot_rounds_deaths() == (42, 3)


@pytest.mark.parametrize("snap", [
    {"round": "x", "deaths": "y"}, {}, {"round": None, "deaths": None},
    {"round": 1.9, "deaths": 2.1}, [1, 2], "bad",
])
def test_snapshot_dirty(sess, snap):
    _write(sess["snap"], snap)
    r, d = session.snapshot_rounds_deaths()
    assert isinstance(r, int) and isinstance(d, int)


# ---------------------------------------------------------------------------
# 展示文案
# ---------------------------------------------------------------------------
def test_describe_lines(sess):
    session.record_end("florr", 10, 1, ["report"], report="本局汇报")
    txt = session.describe()
    assert "当前游戏" in txt and "累计场次" in txt and "本局汇报" in txt


# v2.0 修复：last_report 为 JSON null 时 `None[:80]` 原会 TypeError
@pytest.mark.parametrize("val", [None, "", 0, [], {"a": 1}])
def test_describe_non_string_report(sess, val):
    _write(sess["state"], {"last_report": val, "skills_last": None})
    assert isinstance(session.describe(), str)


def test_stats_text_empty(sess):
    assert "暂无战绩" in session.stats_text()


def test_stats_text_with_records(sess):
    session.record_end("florr", 10, 1, [])
    txt = session.stats_text()
    assert "最近战绩" in txt and "florr" in txt
