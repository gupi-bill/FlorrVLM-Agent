#!/usr/bin/env python3
"""
v2.0 S9 · MCP 工具离线核对脚本 tools/mcp_tools_check.py

用途：不启服务、不发网络请求，一次性核对「README 宣称的工具」是否真的可用。

做三件事：
  1. 列举 MCP 服务端实际注册的工具，与 README 表格逐字比对（多/少/改名都会报）。
  2. 逐个以 mock 参数**真实调用**（走 mcp.call_tool，不是直接调函数），
     记录每个工具是「可用 / 可读错误 / 崩溃」。
  3. 跑一遍 kb_export → kb_import 往返，校验子目录保真与归档归位。

用法：
  python tools/mcp_tools_check.py            # 人类可读报告
  python tools/mcp_tools_check.py --json     # 机器可读（S13 可直接接门禁）
  python tools/mcp_tools_check.py --strict   # 有任何 FAIL 即以退出码 1 结束

依赖：仅 mcp + 本仓库模块；无网络、无 GUI、无 LLM 密钥要求。
"""
import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("UGF_DRY_RUN", "1")

import mcp_server as M  # noqa: E402
import kb_maintainer as K  # noqa: E402

README = os.path.join(ROOT, "README.md")

# 每个工具的一组 mock 参数（尽量走"有意义的分支"而不是纯空参）
MOCK_ARGS = {
    "kb_list": {},
    "kb_search": {"keyword": "BOSS"},
    "kb_write": {"filename": "_s9_probe", "markdown_content": "# S9 探针\n"},
    "kb_append": {"filename": "_s9_probe", "markdown_content": "追加一行\n"},
    "kb_export": {},
    "kb_import": {"backup_path": "__not_exist__.tar.gz"},
    "perceive_game": {},
    "predict_all_entities": {},
    "reset_predictor": {},
    "game_action": {"action_type": "attack"},
    "switch_set": {"set_name": "combat"},
    "handle_afk": {},
    "query_boss_history": {},
    "clean_cache": {"target": "predict"},
    "switch_tactic": {"tactic_file": "player_tactics.md"},
}


def readme_tools():
    """从 README 的 MCP 工具表格里解析出反引号包裹的工具名。"""
    txt = open(README, encoding="utf-8").read()
    m = re.search(r"## 🧩 MCP 工具（(\d+) 个）(.*?)\n---", txt, re.S)
    if not m:
        return None, []
    declared_n = int(m.group(1))
    names = re.findall(r"`([a-z_][a-z0-9_]*)`", m.group(2))
    return declared_n, names


def schema_of(tool):
    return getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}


def check_registry():
    tools = asyncio.run(M.mcp.list_tools())
    actual = [t.name for t in tools]
    declared_n, readme_names = readme_tools()
    rows, ok = [], True
    for name in sorted(set(actual) | set(readme_names)):
        in_code = name in actual
        in_doc = name in readme_names
        if in_code and in_doc:
            state = "OK"
        elif in_code and not in_doc:
            state, ok = "FAIL(代码有/README 未列)", False
        else:
            state, ok = "FAIL(README 列了/代码未注册)", False
        rows.append({"tool": name, "in_code": in_code, "in_doc": in_doc, "state": state})
    if declared_n is not None and declared_n != len(actual):
        ok = False
        rows.append({"tool": f"__heading({declared_n})", "in_code": len(actual),
                     "in_doc": declared_n, "state": "FAIL(标题数量与实际不符)"})
    return tools, rows, ok


def check_callable(tools):
    rows, ok = [], True
    for t in sorted(tools, key=lambda x: x.name):
        name = t.name
        args = MOCK_ARGS.get(name, {})
        try:
            res = asyncio.run(M.mcp.call_tool(name, args))
        except Exception as e:  # noqa: BLE001
            rows.append({"tool": name, "state": f"FAIL(抛异常 {type(e).__name__}: {e})"})
            ok = False
            continue
        text = "\n".join(c.text for c in getattr(res, "content", [])
                         if getattr(c, "type", "") == "text")
        if getattr(res, "is_error", False):
            rows.append({"tool": name, "state": f"FAIL(is_error: {text[:120]})"})
            ok = False
        elif not text.strip():
            rows.append({"tool": name, "state": "FAIL(返回空内容)"})
            ok = False
        else:
            rows.append({"tool": name, "state": "OK",
                         "desc": bool((t.description or "").strip()),
                         "schema": schema_of(t).get("type") == "object",
                         "out": text[:80].replace("\n", " ")})
    return rows, ok


def check_roundtrip():
    """kb_export → kb_import 往返：子目录必须保真，归档不得被复活进活跃库。"""
    tmp = tempfile.mkdtemp(prefix="ugf_s9_")
    try:
        kb = os.path.join(tmp, "knowledge_md")
        arch = os.path.join(tmp, "knowledge_archive")
        os.makedirs(os.path.join(kb, "florr"))
        os.makedirs(arch)
        open(os.path.join(kb, "florr", "boss.md"), "w").write("# florr boss")
        open(os.path.join(kb, "root.md"), "w").write("# root")
        open(os.path.join(arch, "old.md"), "w").write("# archived")
        path = K.export(kb, arch, os.path.join(tmp, "out")).split("到: ")[1].split("（")[0]
        with tarfile.open(path) as t:
            members = t.getnames()
        shutil.rmtree(kb); shutil.rmtree(arch)
        os.makedirs(kb); os.makedirs(arch)
        K.import_backup(kb, arch, path)
        subdir_ok = os.path.isfile(os.path.join(kb, "florr", "boss.md"))
        archive_ok = (not os.path.exists(os.path.join(kb, "old.md"))
                      and os.path.isfile(os.path.join(arch, "old.md")))
        return {
            "members": members,
            "subdir_preserved": subdir_ok,
            "archive_stays_archived": archive_ok,
            "state": "OK" if (subdir_ok and archive_ok) else "FAIL",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--strict", action="store_true", help="存在 FAIL 时退出码 1")
    args = ap.parse_args()

    tools, reg_rows, reg_ok = check_registry()
    call_rows, call_ok = check_callable(tools)
    rt = check_roundtrip()
    all_ok = reg_ok and call_ok and rt["state"] == "OK"

    if args.json:
        print(json.dumps({"ok": all_ok, "sdk": M.MCP_SDK_VERSION, "n_tools": len(tools),
                          "registry": reg_rows, "callable": call_rows, "roundtrip": rt},
                         ensure_ascii=False, indent=2))
        return 0 if (all_ok or not args.strict) else 1

    print(f"MCP SDK 版本: {M.MCP_SDK_VERSION}    实际注册工具: {len(tools)}")
    print("\n== 1. 清单与 README 一致性 ==")
    for r in reg_rows:
        print(f"  {r['state']:<28} {r['tool']}")
    print("\n== 2. 逐工具真实调用 ==")
    for r in call_rows:
        extra = ""
        if r["state"] == "OK":
            extra = f"  desc={'Y' if r['desc'] else 'N'} schema={'Y' if r['schema'] else 'N'}  {r['out']}"
        print(f"  {r['state']:<28} {r['tool']}{extra}")
    print("\n== 3. kb_export / kb_import 往返 ==")
    print(f"  包内成员: {rt['members']}")
    print(f"  子目录保真: {rt['subdir_preserved']}    归档不被复活: {rt['archive_stays_archived']}"
          f"    -> {rt['state']}")
    print(f"\n总计: {'PASS' if all_ok else 'FAIL'}")
    return 0 if (all_ok or not args.strict) else 1


if __name__ == "__main__":
    sys.exit(main())
