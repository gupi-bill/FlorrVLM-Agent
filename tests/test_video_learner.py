"""S19 学习链路离线化测试：抽帧 → 解析 → 入库 → 清理。

本机约束：无 cv2、无 X server、无网络、无 VLM 密钥。本套用例不试图绕开这些约束，
而是**用合成帧 + 可注入 stub 把链路真正跑通**，并断言「小硬盘友好」原则真的生效
（临时目录被清空、无残留）。

所有用例在 tmp_path 内完成，不污染仓库真实目录。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import knowledge_loop
import video_learner


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def env(tmp_path, monkeypatch):
    """重定向知识库与临时帧目录，隔离真实仓库。"""
    kb_dir = tmp_path / "knowledge_md"
    kb_dir.mkdir()
    frames = tmp_path / "video_frames"
    monkeypatch.setattr(video_learner, "KB_DIR", str(kb_dir), raising=False)
    monkeypatch.setattr(knowledge_loop, "KB_DIR", str(kb_dir), raising=False)
    video_learner.set_frame_dir(str(frames))
    video_learner.set_vlm_provider(None)
    yield {"kb": kb_dir, "frames": frames}
    video_learner.set_frame_dir(None)
    video_learner.set_vlm_provider(None)


def _stub(tactic="低血量时立即撤退，不要恋战"):
    return lambda b64: tactic


# ---------------------------------------------------------------------------
# 1. 抽帧环节
# ---------------------------------------------------------------------------
def test_write_png_is_valid_png(env):
    fp = video_learner._write_png(str(env["frames"] / "a.png"), 8, 6, (10, 20, 30))
    with open(fp, "rb") as f:
        head = f.read(8)
    assert head == PNG_MAGIC
    assert os.path.getsize(fp) > 0


def test_synthesize_frames_count_and_names(env):
    frames = video_learner.synthesize_frames(4)
    assert len(frames) == 4
    assert all(os.path.exists(f) for f in frames)
    assert all(f.endswith(".png") for f in frames)
    assert os.path.dirname(frames[0]) == str(env["frames"])


def test_synthesize_frames_are_distinct(env):
    """每帧内容必须不同 —— 全同的帧会掩盖逐帧处理逻辑的缺陷。"""
    frames = video_learner.synthesize_frames(5)
    blobs = []
    for f in frames:
        with open(f, "rb") as fh:
            blobs.append(fh.read())
    assert len(set(blobs)) == 5


def test_synthesize_zero_frames(env):
    assert video_learner.synthesize_frames(0) == []


def test_extract_frames_offline_entry(env):
    frames = video_learner.extract_frames_offline(3)
    assert len(frames) == 3 and all(os.path.exists(f) for f in frames)


def test_extract_frames_without_cv2_returns_empty(env, monkeypatch):
    """真实抽帧在无 cv2 时必须软降级，不能抛 ImportError。"""
    monkeypatch.setattr(video_learner, "CV2_AVAILABLE", False, raising=False)
    assert video_learner.extract_frames("whatever.mp4") == []


def test_image_to_base64_roundtrip(env):
    frames = video_learner.synthesize_frames(1)
    b64 = video_learner.image_to_base64(frames[0])
    assert isinstance(b64, str) and len(b64) > 20


# ---------------------------------------------------------------------------
# 2. VLM 环节（可注入）
# ---------------------------------------------------------------------------
def test_default_vlm_without_key_returns_placeholder(env, monkeypatch):
    monkeypatch.setattr(video_learner, "VLM_API_URL", "", raising=False)
    monkeypatch.setattr(video_learner, "VLM_API_KEY", "", raising=False)
    out = video_learner.vlm_extract_tactic("abc")
    assert out.startswith("[")


def test_vlm_injected_via_param(env, monkeypatch):
    monkeypatch.setattr(video_learner, "VLM_API_URL", "", raising=False)
    assert video_learner.vlm_extract_tactic("abc", provider=_stub("自定义战术")) == "自定义战术"


def test_vlm_injected_via_module(env, monkeypatch):
    monkeypatch.setattr(video_learner, "VLM_API_URL", "", raising=False)
    video_learner.set_vlm_provider(_stub("模块级战术"))
    assert video_learner.vlm_extract_tactic("abc") == "模块级战术"
    video_learner.set_vlm_provider(None)
    assert video_learner.vlm_extract_tactic("abc").startswith("[")


def test_vlm_provider_exception_is_captured(env):
    def boom(_b64):
        raise RuntimeError("vlm down")
    out = video_learner.vlm_extract_tactic("abc", provider=boom)
    assert "失败" in out


def test_stub_vlm_is_deterministic_and_nonempty():
    a = video_learner._stub_vlm("frame-one-content")
    b = video_learner._stub_vlm("frame-one-content")
    assert a == b and a and not a.startswith("[")


# ---------------------------------------------------------------------------
# 3. 入库环节（分区 + 去重）
# ---------------------------------------------------------------------------
def test_kb_target_dir_is_game_partitioned(env, monkeypatch):
    assert video_learner._kb_target_dir("demo") == str(env["kb"] / "demo")
    monkeypatch.setattr("config.active_game", lambda: "active_game")
    assert video_learner._kb_target_dir() == str(env["kb"] / "active_game")


def test_kb_target_dir_sanitizes_name(env):
    assert video_learner._kb_target_dir("a/b c") == str(env["kb"] / "a_b_c")


def test_save_tactics_returns_abs_path_in_partition(env):
    """回归：原先写根目录，导致 S18 之后主循环按游戏分区检索永远找不到。"""
    path = video_learner.save_tactics_to_kb("clip.mp4", ["战术一", "战术二"],
                                            game_name="demo")
    assert os.path.isabs(path)
    assert os.path.dirname(path) == str(env["kb"] / "demo")
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        body = f.read()
    assert "战术一" in body and "战术二" in body


def test_save_tactics_dedups_identical(env):
    video_learner.save_tactics_to_kb("a.mp4", ["同一条战术"], game_name="demo")
    path = video_learner.save_tactics_to_kb("b.mp4", ["同一条战术"], game_name="demo")
    with open(path, encoding="utf-8") as f:
        body = f.read()
    assert "去重后 0 条" in body


def test_save_tactics_filters_placeholders(env):
    path = video_learner.save_tactics_to_kb("c.mp4",
                                            ["[未配置 VLM，跳过]", "真实战术条目"],
                                            game_name="demo")
    with open(path, encoding="utf-8") as f:
        body = f.read()
    assert "未配置" not in body and "真实战术条目" in body


def test_dedup_tolerates_missing_dir(env):
    out = video_learner._dedup_new(["新战术"], kb_dir=str(env["kb"] / "nope"))
    assert out == ["新战术"]


# ---------------------------------------------------------------------------
# 4. 清理环节（小硬盘友好）
# ---------------------------------------------------------------------------
def test_cleanup_returns_true_when_dir_removed(env):
    video_learner.synthesize_frames(3)
    assert os.path.exists(env["frames"])
    assert video_learner.cleanup_temp_frames(quiet=True) is True
    assert not os.path.exists(env["frames"])


def test_cleanup_is_safe_when_dir_absent(env):
    assert video_learner.cleanup_temp_frames(quiet=True) is True


# ---------------------------------------------------------------------------
# 5. 端到端：一次完整学习
# ---------------------------------------------------------------------------
def test_full_pipeline_offline(env):
    res = video_learner.learn_from_video(game="demo", frame_count=5,
                                         vlm_provider=_stub())
    assert res["source"] == "synthetic"
    assert res["frames"] == 5
    assert len(res["tactics"]) == 5
    assert os.path.exists(res["kb_file"])
    assert res["kb_file"].startswith(str(env["kb"] / "demo"))
    # 核心断言：临时帧必须被清干净
    assert res["cleaned"] is True
    assert res["residual"] == []
    assert not os.path.exists(env["frames"])


def test_pipeline_cleans_up_even_when_vlm_fails(env):
    def boom(_b64):
        raise RuntimeError("boom")
    res = video_learner.learn_from_video(game="demo", frame_count=3,
                                         vlm_provider=boom)
    assert len(res["tactics"]) == 3
    assert all("失败" in t for t in res["tactics"])
    assert res["cleaned"] is True and res["residual"] == []


def test_pipeline_keep_frames_keeps_dir_but_no_files(env):
    """cleanup=False 时不删目录，但逐帧删除仍应保证不留任何帧文件。"""
    res = video_learner.learn_from_video(game="demo", frame_count=2,
                                         vlm_provider=_stub(), cleanup=False)
    assert os.path.isdir(env["frames"])          # 目录本身保留
    assert res["residual"] == []                 # 但帧文件已被逐帧删除
    video_learner.cleanup_temp_frames(quiet=True)


def test_pipeline_result_kept_count_matches_file(env):
    res = video_learner.learn_from_video(game="demo", frame_count=4,
                                         vlm_provider=_stub())
    with open(res["kb_file"], encoding="utf-8") as f:
        body = f.read()
    assert f"去重后 {res['kept']} 条" in body


# ---------------------------------------------------------------------------
# 6. 跨阶段闭环：学到的战术必须能被 S18 的检索找到
# ---------------------------------------------------------------------------
def test_learned_tactics_are_retrievable(env):
    """S18 修好分区检索后，S19 学到的战术若还写根目录就永远检索不到。"""
    tactic = "母舰出现时优先集火并保持距离"
    res = video_learner.learn_from_video(game="demo", frame_count=3,
                                         vlm_provider=_stub(tactic))
    assert res["kept"] >= 1

    text, hit = knowledge_loop.retrieve("demo", "母舰")
    assert hit, "学到的战术未被本游戏分区检索命中（学→检索断链）"
    assert tactic in text


def test_learned_tactics_do_not_leak_to_other_game(env):
    video_learner.learn_from_video(game="demo", frame_count=2,
                                   vlm_provider=_stub("独门战术 A"))
    _text, hit = knowledge_loop.retrieve("other", "独门战术")
    assert not hit


def test_learned_tactics_feed_decision(env):
    """学到的战术要能进入决策规则（与 S18 apply_tactics 对齐）。"""
    tactic = "与高威胁目标保持距离，低血量立即撤退"
    res = video_learner.learn_from_video(game="demo", frame_count=2,
                                         vlm_provider=_stub(tactic))
    with open(res["kb_file"], encoding="utf-8") as f:
        body = f.read()
    tactics = knowledge_loop.extract_tactics(body)
    assert "retreat" in tactics or "keep_distance" in tactics
    assert knowledge_loop.apply_tactics("cautious_fight", tactics) == "defend"
