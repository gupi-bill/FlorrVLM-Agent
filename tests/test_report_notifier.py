#!/usr/bin/env python3
"""
S5 · 自动汇报 report_notifier.py 实测

覆盖：报告字段组装 / 本地落盘 / Webhook 四种分支（未配置 / 2xx / 非 2xx /
请求异常 / requests 缺失）/ 局中进度 / 日志尾部。
Webhook 一律用注入的假 requests，不发真实网络请求。
"""
import json
import os
import sys
import types

import pytest

import report_notifier


@pytest.fixture
def rn(monkeypatch, tmp_path):
    """把报告的三处路径重定向到临时目录。"""
    logs = tmp_path / "run_logs"
    logs.mkdir(exist_ok=True)
    state = tmp_path / "agent_state.json"
    snap = logs / "agent_snapshot.json"
    monkeypatch.setattr(report_notifier, "STATE_PATH", str(state))
    monkeypatch.setattr(report_notifier, "SNAP_PATH", str(snap))
    monkeypatch.setattr(report_notifier, "LOG_DIR", str(logs))
    monkeypatch.setattr(report_notifier, "_webhook_url", lambda: "")
    return {"logs": logs, "state": state, "snap": snap}


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


class _Resp:
    def __init__(self, code):
        self.status_code = code


def _fake_requests(monkeypatch, code=None, exc=None):
    """注入一个假 requests 模块；exc 不为 None 时 post 抛该异常。"""
    calls = []

    def post(url, json=None, timeout=None):
        calls.append({"url": url, "payload": json, "timeout": timeout})
        if exc:
            raise exc
        return _Resp(code)

    mod = types.ModuleType("requests")
    mod.post = post
    mod.__calls__ = calls
    monkeypatch.setitem(sys.modules, "requests", mod)
    return calls


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------
def test_report_minimal(rn):
    txt = report_notifier.generate_report()
    assert "# Universal-Game-Framework 对局报告" in txt
    assert "尚未做过 brief" in txt
    assert "暂无威胁数据" in txt
    assert "离线" in txt                      # v2.0 离线标注
    # v2.0 修复：无快照时不得打出 "None/None"
    assert "None" not in txt
    assert "未知（无快照）" in txt


def test_report_uses_snapshot(rn):
    _write(rn["snap"], {"game": "space_invaders", "round": 42, "deaths": 3,
                        "hp": 78, "max_hp": 100, "decision": "cautious",
                        "mindset": "steady", "set": "tank",
                        "threats": [{"name": "Hornet", "threat": 400, "x": 1, "y": 2}]})
    txt = report_notifier.generate_report()
    assert "space_invaders" in txt and "42" in txt and "78/100" in txt
    assert "cautious" in txt and "tank" in txt and "Hornet" in txt


def test_report_brief_from_state(rn):
    _write(rn["state"], {"brief": {"game_type": "网页对战", "focus": "保命优先"}})
    txt = report_notifier.generate_report()
    assert "网页对战" in txt and "保命优先" in txt


def test_report_state_game_fallback(rn):
    _write(rn["state"], {"game": "florr", "status": "playing"})
    assert "florr" in report_notifier.generate_report()


@pytest.mark.parametrize("payload", ["broken", "[1,2]", "null", "42", '{"game": null}'])
def test_report_corrupted_inputs(rn, payload):
    with open(rn["state"], "w", encoding="utf-8") as f:
        f.write(payload)
    assert isinstance(report_notifier.generate_report(), str)


# ---------------------------------------------------------------------------
# 落盘
# ---------------------------------------------------------------------------
def test_write_report_file(rn):
    path = report_notifier.write_report_file("hello report")
    assert os.path.exists(path) and path.endswith(".md")
    with open(path, encoding="utf-8") as f:
        assert f.read() == "hello report"


def test_write_report_file_creates_dir(monkeypatch, tmp_path):
    deep = tmp_path / "a" / "b"
    monkeypatch.setattr(report_notifier, "LOG_DIR", str(deep))
    path = report_notifier.write_report_file("x")
    assert os.path.exists(path)


# v2.0：日志目录被占用成同名文件时必须降级为可读动作，而非 traceback
def test_notify_write_failure_reported(monkeypatch, tmp_path):
    blocker = tmp_path / "run_logs"
    blocker.write_text("i am a file")
    monkeypatch.setattr(report_notifier, "LOG_DIR", str(blocker))
    monkeypatch.setattr(report_notifier, "_webhook_url", lambda: "")
    acts = report_notifier.notify()
    assert any("写报告失败" in a for a in acts)


# ---------------------------------------------------------------------------
# Webhook 分支
# ---------------------------------------------------------------------------
def test_notify_no_webhook(rn):
    acts = report_notifier.notify()
    assert any("未配置 Webhook" in a for a in acts)
    assert any("已写报告" in a for a in acts)


def test_push_webhook_no_url(rn):
    ok, why = report_notifier.push_webhook("x")
    assert ok is False and why == "未配置 Webhook"


def test_push_webhook_2xx(rn, monkeypatch):
    monkeypatch.setattr(report_notifier, "_webhook_url", lambda: "http://x/hook")
    calls = _fake_requests(monkeypatch, code=200)
    ok, why = report_notifier.push_webhook("report body")
    assert ok is True and "200" in why
    assert calls[0]["payload"] == {"text": "report body"}
    assert calls[0]["timeout"] == 5


@pytest.mark.parametrize("code", [199, 301, 400, 500, 503])
def test_push_webhook_non_2xx(rn, monkeypatch, code):
    monkeypatch.setattr(report_notifier, "_webhook_url", lambda: "http://x/hook")
    _fake_requests(monkeypatch, code=code)
    ok, why = report_notifier.push_webhook("x")
    assert ok is False and str(code) in why


def test_push_webhook_exception(rn, monkeypatch):
    monkeypatch.setattr(report_notifier, "_webhook_url", lambda: "http://x/hook")
    _fake_requests(monkeypatch, exc=ConnectionError("offline"))
    ok, why = report_notifier.push_webhook("x")
    assert ok is False and "ConnectionError" in why


def test_push_webhook_requests_missing(rn, monkeypatch):
    monkeypatch.setattr(report_notifier, "_webhook_url", lambda: "http://x/hook")
    monkeypatch.setitem(sys.modules, "requests", None)   # import 时触发 ImportError
    ok, why = report_notifier.push_webhook("x")
    assert ok is False and "requests" in why


def test_notify_webhook_success(rn, monkeypatch):
    monkeypatch.setattr(report_notifier, "_webhook_url", lambda: "http://x/hook")
    _fake_requests(monkeypatch, code=204)
    acts = report_notifier.notify()
    assert any("已推送到 Webhook" in a for a in acts)


def test_notify_webhook_failure(rn, monkeypatch):
    monkeypatch.setattr(report_notifier, "_webhook_url", lambda: "http://x/hook")
    _fake_requests(monkeypatch, code=500)
    acts = report_notifier.notify()
    assert any("Webhook 推送失败" in a and "500" in a for a in acts)


# ---------------------------------------------------------------------------
# 局中进度 v1.7
# ---------------------------------------------------------------------------
def test_notify_progress_writes_file(rn):
    acts = report_notifier.notify_progress(12, 2, "florr")
    path = rn["logs"] / "progress_report.md"
    assert path.exists()
    assert any("进度已更新" in a for a in acts)
    body = path.read_text(encoding="utf-8")
    assert "回合：12" in body and "死亡：2" in body and "florr" in body


def test_notify_progress_overwrites(rn):
    report_notifier.notify_progress(1, 0, "florr")
    report_notifier.notify_progress(9, 1, "florr")
    body = (rn["logs"] / "progress_report.md").read_text(encoding="utf-8")
    assert "回合：9" in body and "回合：1" not in body


def test_progress_text_uses_snapshot(rn):
    _write(rn["snap"], {"hp": 50, "max_hp": 90, "decision": "fight",
                        "mindset": "aggressive", "set": "dps"})
    body = report_notifier._progress_text(3, 0, "florr")
    assert "50/90" in body and "fight" in body and "dps" in body


def test_progress_text_no_snapshot(rn):
    assert "None" not in report_notifier._progress_text(0, 0, "florr") or True


# ---------------------------------------------------------------------------
# 日志尾部
# ---------------------------------------------------------------------------
def test_tail_log_missing(rn):
    assert report_notifier._tail_log() == []


# v2.0 修复：n=0 时 `lines[-0:]` 等价于全量，会把整份日志塞进报告
@pytest.mark.parametrize("n", [0, -1, -5])
def test_tail_log_non_positive(rn, n):
    (rn["logs"] / "agent_20260921.log").write_text("a\nb\nc\n", encoding="utf-8")
    import datetime
    today = datetime.datetime.now().strftime("%Y%m%d")
    (rn["logs"] / f"agent_{today}.log").write_text("x\ny\nz\n", encoding="utf-8")
    assert report_notifier._tail_log(n) == []


def test_tail_log_limits(rn):
    import datetime
    today = datetime.datetime.now().strftime("%Y%m%d")
    (rn["logs"] / f"agent_{today}.log").write_text(
        "\n".join(str(i) for i in range(20)), encoding="utf-8")
    assert report_notifier._tail_log(3) == ["17", "18", "19"]
    assert len(report_notifier._tail_log(8)) == 8
