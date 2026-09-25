# -*- coding: utf-8 -*-
"""S13 · 文档与代码一致性。

目标：让 README / PROJECT_SUMMARY / ROADMAP 三份对外文档"说真话"——
凡文档里写死的结论（用例数、工具数、死亡帧阈值、目录结构、门禁命令、
已验证 / 未验证边界），都必须能被机器复核，防止再次出现"文档超前于代码"。

全部用例零网络、零子进程 pytest，秒级完成。
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOCS = ["README.md", "PROJECT_SUMMARY.md", "ROADMAP.md"]
DEVPLAN_DOCS = [
    "devplan/PLAN.md",
    "devplan/PROGRESS.md",
    "devplan/DIRECTION.md",
    "devplan/OPS.md",
    "devplan/TOOLS.md",
    "devplan/PROFILE_SPEC.md",
]

# 冲刺基线：三份文档必须口径一致地声明同一个数字
BASELINE_CASES = "987"

# 明确禁止再出现的失真表述（历史遗留，已被实测推翻）
FORBIDDEN = [
    "连续 2 帧死亡",       # 实际阈值 8 帧（config.yaml death_frame_threshold）
    "实机已验证",
    "全部功能已完成",
]


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def readme():
    return read("README.md")


@pytest.fixture(scope="module")
def summary():
    return read("PROJECT_SUMMARY.md")


@pytest.fixture(scope="module")
def roadmap():
    return read("ROADMAP.md")


# ---------------------------------------------------------------- 存在性

@pytest.mark.parametrize("rel", DOCS)
def test_doc_exists_and_nontrivial(rel):
    text = read(rel)
    assert len(text.strip()) > 500, "%s 内容过短，疑似被覆盖" % rel


@pytest.mark.parametrize("rel", DEVPLAN_DOCS)
def test_devplan_docs_exist(rel):
    assert os.path.isfile(os.path.join(ROOT, rel)), "缺失冲刺文档 %s" % rel


def test_gate_script_exists_and_covers_all_steps():
    path = os.path.join(ROOT, "scripts", "check.sh")
    assert os.path.isfile(path)
    body = open(path, encoding="utf-8").read()
    for token in ("compileall", "boot_check.py", "game_profile_check.py", "pytest", "--fast"):
        assert token in body, "门禁脚本缺少环节 %s" % token


# ---------------------------------------------------------------- 口径一致

@pytest.mark.parametrize("rel", DOCS)
def test_baseline_case_count_consistent(rel):
    text = read(rel)
    assert BASELINE_CASES in text, "%s 未声明测试基线 %s" % (rel, BASELINE_CASES)


@pytest.mark.parametrize("rel", DOCS)
def test_doc_links_to_progress(rel):
    assert "devplan/PROGRESS.md" in read(rel), "%s 未给出冲刺进度入口" % rel


@pytest.mark.parametrize("rel", DOCS)
def test_doc_discloses_unverified(rel):
    assert "未验证" in read(rel), "%s 未如实披露未验证项" % rel


@pytest.mark.parametrize("rel", DOCS)
def test_no_forbidden_claims(rel):
    text = read(rel)
    for bad in FORBIDDEN:
        assert bad not in text, "%s 仍含失真表述：%s" % (rel, bad)


def test_no_secret_like_literals_in_docs():
    for rel in DOCS:
        text = read(rel)
        assert not re.search(r"\bsk-[A-Za-z0-9]{12,}", text), "%s 疑似包含密钥字面量" % rel


# ---------------------------------------------------------------- README 细节

def test_readme_has_gate_and_offline_sections(readme):
    assert "## ✅ 验证状态" in readme
    assert "## 🧪 离线模式与自测" in readme
    assert "bash scripts/check.sh" in readme
    assert "scripts/check.sh --fast" in readme
    assert "UGF_DRY_RUN=1" in readme
    assert "UGF_PERCEPTION_BACKEND=mock" in readme
    assert "python launcher.py" in readme


def test_readme_death_frame_threshold_matches_config(readme):
    """README 写死的死亡判定帧数必须与 config.yaml 一致。"""
    m = re.search(r"连续 (\d+) 帧判定死亡", readme)
    assert m, "README 未写明死亡判定帧数"
    cfg = read("config.yaml")
    cm = re.search(r"death_frame_threshold:\s*(\d+)", cfg)
    assert cm, "config.yaml 缺少 death_frame_threshold"
    assert int(m.group(1)) == int(cm.group(1)), (
        "README 死亡帧 %s 与 config %s 不一致" % (m.group(1), cm.group(1))
    )


def test_readme_mcp_heading_matches_table(readme):
    m = re.search(r"## 🧩 MCP 工具（(\d+) 个）(.*?)\n---", readme, re.S)
    assert m, "README 缺少 MCP 工具章节"
    declared = int(m.group(1))
    names = re.findall(r"`([a-z_][a-z0-9_]*)`", m.group(2))
    assert declared == len(names), "标题 %d 个与表格 %d 个不符" % (declared, len(names))
    assert declared >= 15


def test_readme_mcp_tools_match_server_registry():
    """README 工具清单必须与 MCP 服务端实际注册清单一致（含标题数量）。"""
    mcp_tools_check = pytest.importorskip("tools.mcp_tools_check")
    _tools, rows, ok = mcp_tools_check.check_registry()
    bad = [r for r in rows if r["state"] != "OK"]
    assert ok, "README 与服务端注册不一致：%s" % bad


def test_readme_file_structure_lists_new_dirs(readme):
    block = readme.split("## 📁 文件结构", 1)[-1].split("\n---", 1)[0]
    for token in ("tests/", "scripts/check.sh", "devplan/", "launcher.py",
                  "ui/legacy/", "game_profiles/", "knowledge_archive/", "run_logs/"):
        assert token in block, "文件结构缺 %s" % token


def test_readme_lists_both_game_profiles(readme):
    block = readme.split("## 📁 文件结构", 1)[-1].split("\n---", 1)[0]
    assert "florr.yaml" in block and "space_invaders.yaml" in block


# ---------------------------------------------------------------- 链接可达性

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


@pytest.mark.parametrize("rel", DOCS)
def test_local_markdown_links_resolve(rel):
    text = read(rel)
    broken = []
    for raw in LINK_RE.findall(text):
        target = raw.split("#", 1)[0].split("?", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        if "*" in target:
            continue
        if not os.path.exists(os.path.join(ROOT, target)):
            broken.append(target)
    assert not broken, "%s 存在失效本地链接：%s" % (rel, broken)


# ---------------------------------------------------------------- 冲刺章节

def test_roadmap_has_sprint_calibration(roadmap):
    assert "v2.0 冲刺校准" in roadmap
    assert "状态口径" in roadmap


def test_summary_has_sprint_section(summary):
    assert "十、v2.0 冲刺实测状态" in summary
    assert "一条命令门禁" in summary


def test_roadmap_v2_scope_is_foundation(roadmap):
    """v2.0 已从"Florr 深度化"改为"地基做实"，文档中必须体现该排期调整。"""
    assert "地基做实" in roadmap
    assert "后置" in roadmap


def test_version_tables_are_qualified(readme, summary):
    """历史版本不能无条件宣称"已完成"，必须带实机未验证限定。"""
    for text in (readme, summary):
        assert "实机未验证" in text


# ---------------------------------------------------------------- 测试套件结构

def test_tests_directory_structure():
    tests_dir = os.path.join(ROOT, "tests")
    files = [f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")]
    assert len(files) >= 14, "测试文件数量异常：%d" % len(files)
    assert os.path.isfile(os.path.join(tests_dir, "conftest.py"))


def test_docs_are_self_checked_by_this_module():
    """S13 自身的交付物必须入库，防止文档同步被回退。"""
    assert os.path.isfile(os.path.join(ROOT, "tests", "test_docs.py"))
