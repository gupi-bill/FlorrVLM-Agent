# -*- coding: utf-8 -*-
"""S23 · 安全与合规加固（离线）。

覆盖四类：
  1. 路径穿越全量复查：档案加载 / 备份导入 / 知识库读写，全部限制在项目内。
  2. 密钥与敏感信息：文档与示例不含真实密钥字面量。
  3. 档案沙箱：非法档案（恶意 YAML tag / 超大数值 / 错误类型）不崩溃，给可读错误。
  4. 合规声明：README / PROJECT_SUMMARY 含「本地/授权环境」合规提醒。

零网络、零真实副作用。
"""
import os
import re
import sys
import tarfile
import io

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import game_profile_check  # noqa: E402

PROFILE_DIR = os.path.normpath(game_profile_check.PROFILE_DIR)

TRAVERSAL_NAMES = [
    "../../etc/passwd",
    "..\\..\\etc\\passwd",
    "a/b/../../../evil",
    "/etc/passwd",
    "..",
    "....//....//etc",
    "",
    "   ",
    "\x00evil",
]


# ------------------------------------------------------------ 1. 路径穿越复查

@pytest.mark.parametrize("bad", TRAVERSAL_NAMES)
def test_profile_path_never_escapes(bad):
    """档案路径经清洗后必须仍在 game_profiles/ 内（S23 修复的穿越缺陷）。"""
    p = os.path.normpath(game_profile_check._profile_path(bad))
    assert os.path.commonpath([p, PROFILE_DIR]) == PROFILE_DIR, \
        f"档案名 {bad!r} 逃出了 {PROFILE_DIR}: {p}"


def test_profile_path_keeps_legit_names():
    """正常档案名不受影响。"""
    for good in ("florr", "space_invaders", "_template", "demo_arcade"):
        p = os.path.normpath(game_profile_check._profile_path(good))
        assert p == os.path.join(PROFILE_DIR, f"{good}.yaml")


def test_import_backup_never_escapes(tmp_path):
    """含 `../` 成员的恶意 tar 不得写到目标根之外。"""
    import kb_maintainer

    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        data = b"# pwned\n"
        for name in ("knowledge_md/../../../../tmp/ugf_pwned.md",
                     "knowledge_md/../../ugf_pwned2.md",
                     "knowledge_md/ok.md"):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    kb = str(tmp_path / "kb")
    arch = str(tmp_path / "arch")
    kb_maintainer.import_backup(kb, arch, str(evil))

    # 断言：没有任何文件被写到 tmp_path 之外
    escaped = [
        "/tmp/ugf_pwned.md", "/tmp/ugf_pwned2.md",
        os.path.join(os.path.dirname(str(tmp_path)), "ugf_pwned2.md"),
    ]
    for f in escaped:
        assert not os.path.exists(f), f"路径穿越写出: {f}"


# ------------------------------------------------------------ 2. 密钥扫描

_SK_PATTERNS = [
    r"sk-[A-Za-z0-9]{16,}",              # OpenAI 风格
    r"ghp_[A-Za-z0-9]{20,}",             # GitHub PAT
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"AKIA[0-9A-Z]{16}",                 # AWS
]


def test_docs_have_no_secret_literals():
    """对外文档不得含真实密钥字面量。"""
    for rel in ("README.md", "PROJECT_SUMMARY.md", "ROADMAP.md", "SECURITY.md"):
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        for pat in _SK_PATTERNS:
            assert not re.search(pat, text), f"{rel} 疑似含密钥: {pat}"


def test_env_example_has_placeholder_only():
    """.env.example 里的密钥必须是占位符，不是真值。"""
    path = os.path.join(ROOT, ".env.example")
    if not os.path.exists(path):
        pytest.skip("无 .env.example")
    text = open(path, encoding="utf-8").read()
    for pat in _SK_PATTERNS:
        assert not re.search(pat, text), f".env.example 含真实密钥: {pat}"


def test_gitignore_excludes_env():
    # 确认 .gitignore 排除 .env（防密钥入库）
    gi = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    assert ".env" in gi


# ------------------------------------------------------------ 3. 档案沙箱

MALICIOUS_PROFILES = {
    "恶意 python tag": "!!python/object/apply:os.system ['echo pwned']\n",
    "超大数值": "game:\n  name: x\npredictor:\n  threat:\n    boss: 1e309\n",
    "game 非映射": "game: [1, 2, 3]\n",
    "根节点非映射": "- just\n- a\n- list\n",
    "空档案": "",
    "循环引用锚点": "a: &x\n  b: *x\n",
}


@pytest.mark.parametrize("label,content", list(MALICIOUS_PROFILES.items()))
def test_malicious_profile_no_crash(label, content, tmp_path, monkeypatch):
    """非法档案不得抛异常；必须返回可读的 errors/warnings。"""
    # 在临时目录里造一个档案，指向它校验（不改动真实 game_profiles/）
    probe = tmp_path / "__probe__.yaml"
    probe.write_text(content, encoding="utf-8")
    monkeypatch.setattr(game_profile_check, "PROFILE_DIR", str(tmp_path))

    try:
        res = game_profile_check.check_detail("__probe__")
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"[{label}] 校验抛异常: {type(e).__name__}: {e}")

    assert isinstance(res, dict)
    assert "ok" in res and "errors" in res
    assert res["ok"] is False
    # 错误必须是非空字符串，不能是 traceback 对象
    for err in res["errors"]:
        assert isinstance(err, str) and err.strip()


# ------------------------------------------------------------ 4. 合规声明

@pytest.mark.parametrize("rel", ["README.md", "PROJECT_SUMMARY.md"])
def test_docs_have_compliance_section(rel):
    """对外文档须含合规声明（本地/授权环境）。"""
    text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
    assert ("授权" in text or "合规" in text or "ToS" in text
            or "服务条款" in text), f"{rel} 缺少合规声明"
