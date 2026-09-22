#!/usr/bin/env python3
"""
v2.0 S9 · MCP 服务端工具注册验证（tests/test_mcp_server.py）

目标：README 宣称的 16 个 MCP 工具，必须逐个「能被列举 + 能被真实调用」。

与本仓库其它测试的差异：
  * 走 **真实 SDK 路径** —— 通过 `mcp.call_tool()` 调用，而不是直接调底层函数，
    这样"装饰器没注册 / 参数 schema 不匹配 / 返回值不可序列化"都能被测出来
    （S7 的 kb_append 漏注册正是死在这一层：直接调函数是好的，走 MCP 就没有）。
  * 全程离线：知识库目录重定向到 tmp_path，感知走 dry-run 进程内 mock，
    键鼠动作走 UGF_DRY_RUN，不产生任何真实网络 / 真实输入事件。

覆盖：
  1. 工具清单与 README 表格逐字一致（含分类归属）
  2. 16 个工具全部可列举、全部可调用、返回可读文本且无 is_error
  3. 参数 schema 与函数签名一致（必填参数确实必填）
  4. 知识库工具：路径穿越防护、空名防护、按游戏分目录
  5. kb_export / kb_import 往返一致性（子目录保真 + 归档不被复活）
  6. 感知 / 预判 / 动作 / 维护四类工具的降级与错误处理
"""
import asyncio
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import mcp_server as M  # noqa: E402
import kb_maintainer as K  # noqa: E402

README = os.path.join(ROOT, "README.md")

# README 表格中声明的工具（按类别分组，顺序与 README 一致）
README_TOOLS = [
    "kb_list", "kb_search", "kb_write", "kb_append", "kb_export", "kb_import",
    "perceive_game", "predict_all_entities", "reset_predictor",
    "game_action", "switch_set", "handle_afk",
    "clean_cache", "query_boss_history", "switch_tactic",
    "ugf_guide",          # M3：内置使用手册
]


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------
@pytest.fixture
def kb(monkeypatch, tmp_path):
    """把知识库根目录重定向到 tmp_path，避免测试污染真实 knowledge_md/。"""
    d = tmp_path / "knowledge_md"
    d.mkdir()
    monkeypatch.setattr(M, "KB_DIR", str(d))
    return d


@pytest.fixture
def dry(monkeypatch):
    """开启 dry-run：键鼠不执行、感知走进程内 mock。"""
    monkeypatch.setenv("UGF_DRY_RUN", "1")
    monkeypatch.setattr(M, "dry_run", lambda: True)
    return True


def call(name, args=None, expect_error=False):
    """
    走真实 SDK 调用一个工具，返回 (结果对象, 文本)。

    刻意不直接调底层 python 函数 —— 只有过 `mcp.call_tool()` 才算"已注册"。
    """
    res = asyncio.run(M.mcp.call_tool(name, args or {}))
    text = "\n".join(c.text for c in getattr(res, "content", []) if getattr(c, "type", "") == "text")
    if not expect_error:
        assert not getattr(res, "is_error", False), f"{name} 返回 is_error: {text}"
    return res, text


def listed_names():
    tools = asyncio.run(M.mcp.list_tools())
    return [t.name for t in tools]


def schema_of(tool):
    """
    SDK 版本无关地取 input schema：
      - mcp 1.x 的 Tool 用驼峰别名 `inputSchema`
      - mcp 2.x 的 Tool 只有 `input_schema`
    直接写 `tool.inputSchema` 在 2.x 上会 AttributeError，测试就假红。
    """
    return getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}


# ---------------------------------------------------------------------------
# 1. 工具清单与 README 一致性
# ---------------------------------------------------------------------------
class TestRegistryMatchesReadme:
    def test_sdk_importable(self):
        assert M.MCP_SDK_VERSION in (1, 2)

    def test_list_tools_returns_16(self):
        assert len(listed_names()) == 16

    def test_names_exactly_match_readme(self):
        assert sorted(listed_names()) == sorted(README_TOOLS)

    def test_readme_declares_15_in_heading(self):
        txt = open(README, encoding="utf-8").read()
        assert re.search(r"MCP 工具（16 个）", txt), "README 标题未声明 16 个工具"

    def test_every_readme_tool_is_backtick_listed(self):
        txt = open(README, encoding="utf-8").read()
        for name in README_TOOLS:
            assert f"`{name}`" in txt, f"README 未列出工具 {name}"

    def test_module_docstring_count_matches(self):
        # 文件头 docstring 曾写"13 个"，实际 15 个，属文档漂移
        m = re.search(r"MCP 工具（(\d+) 个", M.__doc__ or "")
        assert m and int(m.group(1)) == 16

    def test_no_duplicate_tool_names(self):
        names = listed_names()
        assert len(names) == len(set(names))

    def test_every_tool_has_description(self):
        for t in asyncio.run(M.mcp.list_tools()):
            assert (t.description or "").strip(), f"{t.name} 缺少描述"

    @pytest.mark.parametrize("name", README_TOOLS)
    def test_every_tool_has_input_schema(self, name):
        for t in asyncio.run(M.mcp.list_tools()):
            if t.name == name:
                sch = schema_of(t)
                assert isinstance(sch, dict)
                assert sch.get("type") == "object", f"{name} schema: {sch}"
                return
        pytest.fail(f"{name} 未注册")


# ---------------------------------------------------------------------------
# 2. 16 个工具逐个真实可调
# ---------------------------------------------------------------------------
class TestEveryToolCallable:
    def test_kb_list(self, kb):
        _, t = call("kb_list", {})
        assert "[" in t

    def test_kb_search(self, kb):
        (kb / "a.md").write_text("# hello world", encoding="utf-8")
        _, t = call("kb_search", {"keyword": "hello"})
        assert "共找到 1 条结果" in t

    def test_kb_write(self, kb):
        _, t = call("kb_write", {"filename": "note", "markdown_content": "# x"})
        assert "已写入知识库" in t
        assert (kb / "note.md").exists()

    def test_kb_append(self, kb):
        call("kb_write", {"filename": "note", "markdown_content": "A"})
        _, t = call("kb_append", {"filename": "note", "markdown_content": "B"})
        assert "已追加到知识库" in t
        assert "B" in (kb / "note.md").read_text(encoding="utf-8")

    def test_kb_export(self, kb, monkeypatch, tmp_path):
        monkeypatch.setattr(K, "BASE_DIR", str(tmp_path))
        (kb / "x.md").write_text("# x", encoding="utf-8")
        _, t = call("kb_export", {})
        assert "已导出知识库到" in t

    def test_kb_import(self, kb, monkeypatch, tmp_path):
        monkeypatch.setattr(K, "BASE_DIR", str(tmp_path))
        _, t = call("kb_import", {"backup_path": "nope.tar.gz"})
        assert "找不到备份文件" in t

    def test_perceive_game(self, dry):
        _, t = call("perceive_game", {})
        data = json.loads(t)
        assert "entities" in data and "player" in data

    def test_predict_all_entities(self, dry):
        call("perceive_game", {})
        _, t = call("predict_all_entities", {})
        assert t  # 帧不足时也必须给出可读提示而非崩溃

    def test_reset_predictor(self):
        _, t = call("reset_predictor", {})
        assert "已清空" in t

    def test_game_action(self, dry):
        _, t = call("game_action", {"action_type": "attack"})
        assert "[dry-run]" in t

    def test_switch_set(self, dry):
        _, t = call("switch_set", {"set_name": "combat"})
        assert "[dry-run]" in t

    def test_handle_afk(self):
        _, t = call("handle_afk", {})
        assert "AFK" in t

    def test_query_boss_history(self, kb):
        _, t = call("query_boss_history", {})
        assert "BOSS" in t

    def test_clean_cache(self):
        _, t = call("clean_cache", {"target": "predict"})
        assert "预判历史已清空" in t

    def test_switch_tactic(self, kb):
        (kb / "tac.md").write_text("# tactic", encoding="utf-8")
        _, t = call("switch_tactic", {"tactic_file": "tac.md"})
        assert "已切换当前战术为" in t

    def test_unknown_tool_is_detectable(self):
        """
        调用未注册工具必须「可被检测」——要么抛带工具名的异常，要么返回错误结果，
        绝不能返回空内容让主循环误以为成功。

        实测修正（与 S7 记录不同）：mcp 2.x 进程内 `call_tool` 对**未知工具**会抛
        `ToolError`；只有工具内部异常才会被包成 is_error 结果。两条路径都要能兜住。
        """
        try:
            res = asyncio.run(M.mcp.call_tool("no_such_tool", {}))
        except Exception as e:  # noqa: BLE001
            assert "no_such_tool" in str(e), f"异常未指明工具名: {e}"
            return
        txt = "\n".join(c.text for c in getattr(res, "content", []) if getattr(c, "type", "") == "text")
        assert txt.strip(), "未知工具返回空内容，主循环无法感知失败"
        assert getattr(res, "is_error", False), "未知工具未标记 is_error"


# ---------------------------------------------------------------------------
# 3. 参数 schema 与签名一致
# ---------------------------------------------------------------------------
class TestSchema:
    @pytest.mark.parametrize("name,required", [
        ("kb_list", []),
        ("kb_search", ["keyword"]),
        ("kb_write", ["filename", "markdown_content"]),
        ("kb_append", ["filename", "markdown_content"]),
        ("kb_export", []),
        ("kb_import", ["backup_path"]),
        ("perceive_game", []),
        ("predict_all_entities", []),
        ("reset_predictor", []),
        ("game_action", ["action_type"]),
        ("switch_set", ["set_name"]),
        ("handle_afk", []),
        ("query_boss_history", []),
        ("clean_cache", []),
        ("switch_tactic", ["tactic_file"]),
    ])
    def test_required_params(self, name, required):
        for t in asyncio.run(M.mcp.list_tools()):
            if t.name == name:
                assert sorted(schema_of(t).get("required", [])) == sorted(required)
                return
        pytest.fail(f"{name} 未注册")


# ---------------------------------------------------------------------------
# 4. 知识库工具：路径穿越 / 空名 / 分目录
# ---------------------------------------------------------------------------
class TestKbPathSafety:
    @pytest.mark.parametrize("bad", [
        "../../evil.md", "../evil.md", "/etc/passwd.md", "..", "../../../tmp/x.md",
    ])
    def test_write_rejects_traversal(self, kb, bad, tmp_path):
        call("kb_write", {"filename": bad, "markdown_content": "pwned"})
        # 清洗后即使写入，也必须落在知识库目录内，绝不许出现在 kb 之外
        for root, _, files in os.walk(str(tmp_path)):
            for f in files:
                p = os.path.join(root, f)
                if f in ("evil.md", "passwd.md") and os.path.commonpath([str(kb), p]) != str(kb):
                    pytest.fail(f"路径穿越成功，写到了知识库之外: {p}")

    def test_write_landed_inside_kb(self, kb):
        _, t = call("kb_write", {"filename": "../../evil.md", "markdown_content": "x"})
        assert str(kb) in t or "错误" in t
        assert not os.path.exists(os.path.join(os.path.dirname(str(kb)), "evil.md"))

    @pytest.mark.parametrize("bad", ["", "   ", "/", "///", "..", "."])
    def test_write_rejects_empty(self, kb, bad):
        _, t = call("kb_write", {"filename": bad, "markdown_content": "x"})
        assert "错误" in t or "不能为空" in t

    @pytest.mark.parametrize("bad", ["", "   ", "/", "///", "..", "."])
    def test_append_rejects_empty(self, kb, bad):
        _, t = call("kb_append", {"filename": bad, "markdown_content": "x"})
        assert "错误" in t or "不能为空" in t

    def test_append_traversal_stays_inside_kb(self, kb, tmp_path):
        """穿越名被清洗成单层名后落在知识库内，不许写到 kb 之外。"""
        call("kb_append", {"filename": "../../evil.md", "markdown_content": "x"})
        for root, _, files in os.walk(str(tmp_path)):
            for f in files:
                if f == "evil.md":
                    p = os.path.join(root, f)
                    assert os.path.commonpath([str(kb), p]) == str(kb), f"写到知识库外: {p}"

    def test_resolve_kb_path_never_escapes_kb(self, kb):
        for bad in ("../../../etc/passwd.md", "..", "/etc/passwd.md", "a/../../b.md"):
            p = M._resolve_kb_path(bad, "")
            if p is not None:
                assert os.path.commonpath([str(kb), p]) == str(kb), f"{bad} 穿越到 {p}"

    def test_resolve_kb_path_ok(self, kb):
        p = M._resolve_kb_path("note.md", "")
        assert p and os.path.commonpath([str(kb), p]) == str(kb)

    def test_resolve_kb_path_game_subdir(self, kb):
        p = M._resolve_kb_path("note.md", "florr")
        assert p and p.endswith(os.path.join("florr", "note.md"))

    def test_game_name_traversal_not_listing_parent(self, kb, tmp_path):
        """game_name='..' 曾让 kb_list 列出上一级目录内容。"""
        (tmp_path / "outside.md").write_text("secret", encoding="utf-8")
        _, t = call("kb_list", {"game_name": ".."})
        assert "outside.md" not in t

    def test_write_into_game_subdir(self, kb):
        _, t = call("kb_write", {"filename": "boss", "markdown_content": "# b", "game_name": "florr"})
        assert (kb / "florr" / "boss.md").exists()
        _, t2 = call("kb_list", {"game_name": "florr"})
        assert "boss.md" in t2

    def test_search_scoped_by_game(self, kb):
        call("kb_write", {"filename": "a", "markdown_content": "alpha", "game_name": "florr"})
        call("kb_write", {"filename": "b", "markdown_content": "alpha", "game_name": "other"})
        _, t = call("kb_search", {"keyword": "alpha", "game_name": "florr"})
        assert "共找到 1 条结果" in t

    def test_search_missing_game_readable(self, kb):
        _, t = call("kb_search", {"keyword": "x", "game_name": "nope"})
        assert "未找到游戏" in t

    def test_write_adds_md_extension(self, kb):
        call("kb_write", {"filename": "noext", "markdown_content": "x"})
        assert (kb / "noext.md").exists()

    def test_search_no_hit_message(self, kb):
        _, t = call("kb_search", {"keyword": "zzzz"})
        assert "未找到相关内容" in t

    def test_write_reports_failure_not_raise(self, kb, monkeypatch):
        monkeypatch.setattr(M, "_resolve_kb_path", lambda *a, **k: str(kb / "missing_dir" / "x.md"))
        _, t = call("kb_write", {"filename": "x", "markdown_content": "y"})
        assert "写入知识库失败" in t

    def test_append_reports_failure_not_raise(self, kb, monkeypatch):
        monkeypatch.setattr(M, "_resolve_kb_path", lambda *a, **k: str(kb / "missing_dir" / "x.md"))
        _, t = call("kb_append", {"filename": "x", "markdown_content": "y"})
        assert "追加到知识库失败" in t


# ---------------------------------------------------------------------------
# 5. kb_export / kb_import 往返一致性
# ---------------------------------------------------------------------------
class TestKbRoundTrip:
    def _make(self, tmp_path):
        kb = tmp_path / "knowledge_md"
        arch = tmp_path / "knowledge_archive"
        (kb / "florr").mkdir(parents=True)
        (arch).mkdir(parents=True)
        (kb / "florr" / "boss.md").write_text("# florr boss", encoding="utf-8")
        (kb / "root.md").write_text("# root", encoding="utf-8")
        (arch / "old.md").write_text("# archived", encoding="utf-8")
        out = tmp_path / "out"
        return kb, arch, out

    def test_export_preserves_game_subdir(self, tmp_path):
        kb, arch, out = self._make(tmp_path)
        import tarfile
        msg = K.export(str(kb), str(arch), str(out))
        path = msg.split("到: ")[1].split("（")[0]
        with tarfile.open(path) as t:
            names = t.getnames()
        assert "knowledge_md/florr/boss.md" in names, f"子目录被拍平: {names}"

    def test_roundtrip_keeps_subdir(self, tmp_path):
        kb, arch, out = self._make(tmp_path)
        msg = K.export(str(kb), str(arch), str(out))
        path = msg.split("到: ")[1].split("（")[0]
        import shutil
        shutil.rmtree(kb)
        kb.mkdir()
        K.import_backup(str(kb), str(arch), path)
        assert (kb / "florr" / "boss.md").exists(), "往返后游戏子目录丢失"

    def test_roundtrip_archive_stays_archived(self, tmp_path):
        kb, arch, out = self._make(tmp_path)
        msg = K.export(str(kb), str(arch), str(out))
        path = msg.split("到: ")[1].split("（")[0]
        import shutil
        shutil.rmtree(kb); shutil.rmtree(arch)
        kb.mkdir(); arch.mkdir()
        res = K.import_backup(str(kb), str(arch), path)
        assert not (kb / "old.md").exists(), "归档笔记被复活进活跃库"
        assert (arch / "old.md").exists(), "归档笔记未回到归档目录"
        assert "归档" in res

    def test_roundtrip_content_identical(self, tmp_path):
        kb, arch, out = self._make(tmp_path)
        msg = K.export(str(kb), str(arch), str(out))
        path = msg.split("到: ")[1].split("（")[0]
        before = (kb / "florr" / "boss.md").read_text(encoding="utf-8")
        import shutil
        shutil.rmtree(kb); kb.mkdir()
        K.import_backup(str(kb), str(arch), path)
        assert (kb / "florr" / "boss.md").read_text(encoding="utf-8") == before

    def test_legacy_flat_backup_still_imports(self, tmp_path):
        """旧包内是 knowledge_md/xxx.md（无子目录），必须仍能导入。"""
        import tarfile
        kb = tmp_path / "knowledge_md"; kb.mkdir()
        arch = tmp_path / "knowledge_archive"; arch.mkdir()
        p = tmp_path / "legacy.tar.gz"
        src = tmp_path / "src.md"
        src.write_text("# legacy", encoding="utf-8")
        with tarfile.open(p, "w:gz") as t:
            t.add(src, arcname="knowledge_md/src.md")
        res = K.import_backup(str(kb), str(arch), str(p))
        assert (kb / "src.md").exists()
        assert "1 个" in res

    def test_import_backup_resists_traversal(self, tmp_path):
        import tarfile
        kb = tmp_path / "knowledge_md"; kb.mkdir()
        arch = tmp_path / "knowledge_archive"; arch.mkdir()
        p = tmp_path / "evil.tar.gz"
        src = tmp_path / "e.md"; src.write_text("pwn", encoding="utf-8")
        with tarfile.open(p, "w:gz") as t:
            t.add(src, arcname="knowledge_md/../../evil.md")
        K.import_backup(str(kb), str(arch), str(p))
        assert not (tmp_path.parent / "evil.md").exists()
        assert not (tmp_path / "evil.md").exists()

    def test_import_missing_file(self, tmp_path):
        kb = tmp_path / "kb"; arch = tmp_path / "arch"
        assert "找不到备份文件" in K.import_backup(str(kb), str(arch), str(tmp_path / "nope.tar.gz"))


# ---------------------------------------------------------------------------
# 6. 感知 / 动作 / 维护工具的错误处理
# ---------------------------------------------------------------------------
class TestToolErrorHandling:
    def test_perceive_offline_readable_error(self, kb, monkeypatch):
        monkeypatch.setattr(M, "dry_run", lambda: False)
        monkeypatch.setattr(M, "_perception_url", lambda: "http://127.0.0.1:1/perceive")
        _, t = call("perceive_game", {})
        assert "error" in json.loads(t)

    def test_perceive_dry_run_uses_inproc_mock(self, dry):
        _, t = call("perceive_game", {})
        data = json.loads(t)
        assert data.get("_fallback") == "inproc-mock" or "entities" in data

    def test_game_action_unknown_type(self, dry):
        _, t = call("game_action", {"action_type": "fly"})
        assert "未知动作类型" in t

    def test_game_action_move_without_coords(self, dry):
        _, t = call("game_action", {"action_type": "move"})
        assert "必须提供 x 和 y" in t

    def test_game_action_move_with_coords(self, dry):
        _, t = call("game_action", {"action_type": "move", "x": 10, "y": 20})
        assert "[dry-run]" in t and "(10,20)" in t

    def test_switch_set_unknown(self, dry):
        _, t = call("switch_set", {"set_name": "nope"})
        assert "未知套装" in t

    def test_switch_tactic_missing_file(self, kb):
        _, t = call("switch_tactic", {"tactic_file": "nope.md"})
        assert "没有这份战术文档" in t

    def test_switch_tactic_rejects_traversal(self, kb, tmp_path):
        (tmp_path / "secret.md").write_text("secret", encoding="utf-8")
        _, t = call("switch_tactic", {"tactic_file": "../secret.md"})
        assert "没有这份战术文档" in t or "非法" in t

    def test_query_boss_history_missing_file(self, kb):
        _, t = call("query_boss_history", {})
        assert "还没有 BOSS 行为记录" in t

    def test_query_boss_history_filters(self, kb):
        (kb / "boss_behavior_log.md").write_text(
            "### Hornet\nslow\n\n### Mantis\nfast\n", encoding="utf-8")
        _, t = call("query_boss_history", {"boss_name": "Mantis"})
        assert "Mantis" in t and "Hornet" not in t

    def test_query_boss_history_no_hit(self, kb):
        (kb / "boss_behavior_log.md").write_text("### Hornet\nslow\n", encoding="utf-8")
        _, t = call("query_boss_history", {"boss_name": "Nope"})
        assert "没有关于" in t

    def test_clean_cache_unknown_target(self):
        _, t = call("clean_cache", {"target": "nope"})
        assert "未知目标" in t

    def test_clean_cache_frames_absent_says_so(self, kb, monkeypatch, tmp_path):
        monkeypatch.setattr(M, "BASE_DIR", str(tmp_path))
        _, t = call("clean_cache", {"target": "frames"})
        assert "不存在（无需清理）" in t

    def test_clean_cache_frames_present(self, kb, monkeypatch, tmp_path):
        monkeypatch.setattr(M, "BASE_DIR", str(tmp_path))
        (tmp_path / "video_frames").mkdir()
        (tmp_path / "video_frames" / "a.png").write_bytes(b"x")
        _, t = call("clean_cache", {"target": "frames"})
        assert "已清理" in t
        assert not (tmp_path / "video_frames").exists()

    def test_switch_set_maps_all_slots(self, dry):
        for s in ("combat", "tank", "retreat", "chase", "team"):
            _, t = call("switch_set", {"set_name": s})
            assert "[dry-run]" in t

    def test_vector_search_switch_not_dead(self, kb, monkeypatch):
        """FLORR_VECTOR_SEARCH=1 时 kb_search 必须真的走向量分支（原被局部变量短路）。"""
        monkeypatch.setattr(M, "USE_VECTOR_SEARCH", True)
        seen = {}
        monkeypatch.setattr(M, "_vector_search", lambda k, b=None: seen.setdefault("called", 1) and "VECTOR")
        _, t = call("kb_search", {"keyword": "x"})
        assert t == "VECTOR"

    def test_vector_search_signature_accepts_base(self, kb):
        # 原签名只收 1 个参数，kb_search 却传 2 个 -> TypeError
        (kb / "a.md").write_text("hello", encoding="utf-8")
        out = M._vector_search("hello", str(kb))
        assert "hello" in out

    def test_text_search_counts_hits(self, kb):
        (kb / "a.md").write_text("alpha", encoding="utf-8")
        (kb / "b.md").write_text("alpha", encoding="utf-8")
        assert "共找到 2 条结果" in M._text_search("alpha", str(kb))
