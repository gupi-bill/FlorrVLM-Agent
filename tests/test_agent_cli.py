#!/usr/bin/env python3
"""
S8 · CLI 全命令冒烟回归测试（tests/test_agent_cli.py）

定位：锁定 `agent_cli.py` 在 S8 冒烟中暴露的缺陷，防止回归。

离线约束：
  - 不发起任何真实网络请求；不依赖 .env / LLM / VLM / YOLO。
  - 落盘路径（会话档案 / 知识库 / 日志）全部经 monkeypatch 重定向到 tmp_path。
  - stdin 一律视为非交互，禁止任何 input() 阻塞。

回归锁定的缺陷（均来自 `tools/cli_smoke.py` 实测）：
  C1 `_append_log` 未定义 → kb_list <不存在的游戏> 直接 NameError 崩溃
  C2 `-c brief` 在 stdin 可交互时永久阻塞在 input()
  C3 `-c` 模式下 help / play / auto 三个命令均落到"未知命令"
  C4 `ui_pyqt.py` 的 `--auto search <game> <query>` 调用形状 CLI 完全不支持
  C5 `unload` 跨进程不恢复技能 → 显式卸载恒返回"未加载"
  C6 kb_* 系列命令无法传第二参数（游戏名），`kb_search boss florr` 变成搜 "boss florr"
  C7 交互模式下 kb_list/kb_search/kb_write/kb_append 四个命令全是"未知命令"
  C8 帮助清单 HELP_LINES 漏登记 4 个 kb_* 命令
  C9 `_run_auto` 的 return 之后有 28 行完全重复的死代码
"""
import json
import os
import sys

import pytest

import agent_cli
import config


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """把所有落盘路径重定向到临时目录，避免污染仓库与 config 加载优先级。"""
    monkeypatch.setattr(agent_cli, "STATE_FILE", str(tmp_path / "agent_state.json"))
    monkeypatch.setattr(agent_cli, "KB_DIR", str(tmp_path / "knowledge_md"))
    monkeypatch.setattr(agent_cli, "_ONE_SHOT", True)   # 测试环境永不交互
    monkeypatch.setattr(config, "TUNED_PATH", str(tmp_path / "tuned_overrides.yaml"))
    os.makedirs(str(tmp_path / "knowledge_md"), exist_ok=True)
    yield tmp_path


@pytest.fixture
def logs_dir(tmp_path, monkeypatch):
    d = tmp_path / "run_logs"
    d.mkdir(exist_ok=True)
    monkeypatch.setattr(config, "get",
                        lambda k, dflt=None: str(d) if k == "paths.run_logs" else dflt,
                        raising=True)
    return d


# ---------------------------------------------------------------------------
# C1 · _append_log 回归（NameError 崩溃）
# ---------------------------------------------------------------------------
def test_append_log_symbol_exists():
    assert callable(getattr(agent_cli, "_append_log", None)), \
        "_append_log 必须存在：kb_list / kb_search 都在调用它"


def test_append_log_writes_file(logs_dir):
    agent_cli._append_log("hello-s8")
    files = [f for f in os.listdir(str(logs_dir)) if f.startswith("agent_")]
    assert files, "日志未落盘"
    body = open(os.path.join(str(logs_dir), files[0]), encoding="utf-8").read()
    assert "hello-s8" in body


def test_append_log_never_raises(monkeypatch, tmp_path):
    """日志目录被占成同名文件、或 config 异常时，必须静默吞掉。"""
    monkeypatch.setattr(config, "get", lambda k, d=None: (_ for _ in ()).throw(RuntimeError("boom")))
    agent_cli._append_log("x")            # 不得抛异常
    agent_cli._append_log("")             # 空消息同样不抛


def test_kb_list_missing_game_dir_no_crash():
    """C1 主回归：走到 `_append_log` 分支时不得 NameError。"""
    out = agent_cli._cmd_kb_list("no_such_game_xyz")
    assert "知识库暂无文档" in out


def test_kb_list_missing_root_dir_no_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_cli, "KB_DIR", str(tmp_path / "nope"))
    out = agent_cli._cmd_kb_list("")
    assert "知识库暂无文档" in out


# ---------------------------------------------------------------------------
# C2 · 非交互模式不得阻塞（input 回归）
# ---------------------------------------------------------------------------
def test_is_interactive_false_in_one_shot(monkeypatch):
    monkeypatch.setattr(agent_cli, "_ONE_SHOT", True)
    assert agent_cli._is_interactive() is False
    monkeypatch.setattr(agent_cli, "_ONE_SHOT", False)
    assert isinstance(agent_cli._is_interactive(), bool)


def test_collect_brief_non_interactive_returns_all_keys(monkeypatch):
    monkeypatch.setattr(agent_cli, "_ONE_SHOT", True)
    monkeypatch.delenv("UGF_BRIEF_GAME_TYPE", raising=False)
    monkeypatch.delenv("UGF_BRIEF_FOCUS", raising=False)
    monkeypatch.delenv("UGF_BRIEF_WATCH_OUT", raising=False)
    brief = agent_cli._collect_brief(None)
    assert set(brief) == {"game_type", "focus", "watch_out"}
    assert all(v == "" for v in brief.values())


def test_collect_brief_reads_env(monkeypatch):
    monkeypatch.setattr(agent_cli, "_ONE_SHOT", True)
    monkeypatch.setenv("UGF_BRIEF_FOCUS", "打Boss")
    brief = agent_cli._collect_brief(None)
    assert brief["focus"] == "打Boss"


def test_cmd_brief_non_interactive(monkeypatch):
    monkeypatch.setattr(agent_cli, "_ONE_SHOT", True)
    out = agent_cli._cmd_brief()
    assert "brief" in out
    st = agent_cli.load_state()
    assert set(st["brief"]) == {"game_type", "focus", "watch_out"}


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,kw,game", [
    ("boss", "boss", ""),
    ("boss florr", "boss", "florr"),
    ("", "", ""),
    ("a b c", "a", "b c"),
    ("  boss   florr  ", "boss", "florr"),
])
def test_arg2(raw, kw, game):
    assert agent_cli._arg2(raw) == (kw, game)


def test_offline_note_text():
    assert "dry-run" in agent_cli._offline_note("联网资料检索")


# ---------------------------------------------------------------------------
# C6 · kb_* 第二参数（游戏名）
# ---------------------------------------------------------------------------
def test_kb_search_two_args_uses_game_dir():
    """回归：原先 "boss florr" 被当成单个关键词，搜成了 'boss florr'。"""
    out = agent_cli._cmd_kb_search("boss florr")
    assert "未找到游戏 florr 的知识库" in out


def test_kb_search_one_arg_searches_root():
    p = os.path.join(agent_cli.KB_DIR, "note.md")
    open(p, "w", encoding="utf-8").write("# note\nBOSS_TACTIC_MARKER\n")
    out = agent_cli._cmd_kb_search("BOSS_TACTIC_MARKER")
    assert "note.md" in out


def test_kb_write_two_args_targets_game_dir():
    out = agent_cli._cmd_kb_write("t.md florr")
    assert os.path.isfile(os.path.join(agent_cli.KB_DIR, "florr", "t.md"))
    assert "✅" in out


def test_kb_write_one_arg_targets_root():
    agent_cli._cmd_kb_write("t.md")
    assert os.path.isfile(os.path.join(agent_cli.KB_DIR, "t.md"))


def test_kb_append_two_args_targets_game_dir():
    agent_cli._cmd_kb_append("t.md florr")
    agent_cli._cmd_kb_append("t.md florr")
    p = os.path.join(agent_cli.KB_DIR, "florr", "t.md")
    assert os.path.isfile(p)
    assert open(p, encoding="utf-8").read().count("# 追加内容") == 2


def test_kb_write_adds_md_suffix():
    agent_cli._cmd_kb_write("no_ext")
    assert os.path.isfile(os.path.join(agent_cli.KB_DIR, "no_ext.md"))


# ---------------------------------------------------------------------------
# C3 / C8 · 命令注册表一致性
# ---------------------------------------------------------------------------
def _help_cmds():
    cmds = set()
    for spec, _d in agent_cli.HELP_LINES:
        head = spec.split()[0]
        for part in head.split("/"):        # "load/unload/run_skill" → 三个
            cmds.add(part.strip())
    return cmds


INTERACTIVE_ONLY = {"quit", "exit", "q", "h", "?"}


def test_every_documented_cmd_has_handler():
    reg = agent_cli._command_registry("")
    missing = sorted(c for c in _help_cmds()
                     if c not in reg and c not in INTERACTIVE_ONLY)
    assert not missing, f"帮助里写了但没有实现（C3 类缺陷）: {missing}"


def test_kb_commands_documented():
    """C8 回归：4 个 kb_* 命令此前完全没进 HELP_LINES。"""
    cmds = _help_cmds()
    for c in ("kb_list", "kb_write", "kb_append", "kb_search"):
        assert c in cmds, f"{c} 未登记进帮助清单"


def test_kb_commands_in_registry():
    reg = agent_cli._command_registry("")
    for c in ("kb_list", "kb_write", "kb_append", "kb_search"):
        assert c in reg


def test_registry_has_play_auto_help():
    reg = agent_cli._command_registry("")
    for c in ("play", "auto", "help"):
        assert c in reg, f"-c 模式缺少命令 {c}（C3 回归）"


def test_interactive_dispatch_covers_kb(monkeypatch):
    """C7 回归：交互模式原先没有 kb_* 分支。"""
    src = open(agent_cli.__file__, encoding="utf-8").read()
    for c in ("kb_list", "kb_search", "kb_write", "kb_append"):
        assert f'elif cmd == "{c}":' in src, f"交互模式缺少 {c} 分支"


def test_no_dead_code_after_auto_return():
    """C9 回归：`_run_auto` 的 return 之后不得再有可执行代码。"""
    import ast
    tree = ast.parse(open(agent_cli.__file__, encoding="utf-8").read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_run_auto")
    last = fn.body[-1]
    assert isinstance(last, ast.Return), "函数最后一条语句必须是 return（无死代码）"


# ---------------------------------------------------------------------------
# C5 · unload 跨进程恢复
# ---------------------------------------------------------------------------
def test_unload_restores_from_state():
    """回归：一次性调用下内存无技能，原先 unload 恒返回"未加载"。"""
    agent_cli._cmd_load("report")
    assert "report" in agent_cli.load_state()["skills_active"]
    agent_cli.SKILLS.unload("report")          # 模拟"新进程"：内存清空
    assert not agent_cli.SKILLS.is_loaded("report")
    out = agent_cli._cmd_unload("report")
    assert "已卸载" in out, out


def test_unload_unknown_skill_readable():
    out = agent_cli._cmd_unload("no_such_skill_xyz")
    assert isinstance(out, str) and out.strip()


# ---------------------------------------------------------------------------
# C4 · --auto search 调用形状
# ---------------------------------------------------------------------------
def test_run_auto_search_runs_chain():
    out = agent_cli._run_auto_search("florr", "basic guide")
    assert "当前游戏已设为" in out
    assert "ensure" in out or "开玩前检查" in out


def test_cli_auto_search_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["agent_cli.py", "--auto", "search", "florr", "basic", "guide"])
    agent_cli.main()
    assert "当前游戏已设为" in capsys.readouterr().out


def test_cli_auto_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["agent_cli.py", "--auto", "florr"])
    agent_cli.main()
    assert "开玩前检查" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 一次性调用入口行为
# ---------------------------------------------------------------------------
def test_unknown_command_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["agent_cli.py", "-c", "definitely_not_a_cmd"])
    with pytest.raises(SystemExit) as e:
        agent_cli.main()
    assert e.value.code == 1
    assert "未知命令" in capsys.readouterr().out


def test_help_command_prints_table(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["agent_cli.py", "-c", "help"])
    agent_cli.main()
    out = capsys.readouterr().out
    assert "detect" in out and "kb_search" in out


def test_state_command_returns_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["agent_cli.py", "-c", "state"])
    agent_cli.main()
    st = json.loads(capsys.readouterr().out)
    assert st["game"] == agent_cli.ACTIVE_GAME


# ---------------------------------------------------------------------------
# 基础命令离线可读性（无 traceback、有实际内容）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cmd", [
    "capabilities", "detect florr", "ensure", "research",
    "validate florr", "kb_list", "stats", "report", "session",
    "resume", "skills", "run_skill report",
])
def test_commands_return_readable_text(cmd, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["agent_cli.py", "-c", cmd])
    agent_cli.main()
    out = capsys.readouterr().out
    assert "Traceback" not in out
    # 中文短提示（如"无待续玩进度"6 字）也算可读输出，阈值按最短有效回复定
    assert len(out.strip()) >= 5, f"{cmd} 输出为空"


def test_detect_persists_game():
    agent_cli._cmd_detect("SPACE_INVADERS")
    assert agent_cli.load_state()["game"] == "space_invaders"
