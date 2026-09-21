# S19 · 学习链路离线化（视频 → 战术入库）

> 执行时间：2026-09-22 06:12~06:4x（F 线） ｜ 环境：无 cv2 / 无网络 / 无 VLM 密钥
> 交付：`video_learner.py` 可注入改造、`tests/test_video_learner.py`（27 用例）、本文

## 1. 结论先行

`video_learner` / `video_sources` 此前**从未跑通过**：抽帧依赖 cv2（本机无）、VLM 依赖密钥
（本机无）、入库路径与 S18 之后的分区检索不一致。本阶段用**合成帧 + 可注入 stub** 把
「抽帧 → 解析 → 入库 → 清理」整条链路在本机真正跑通，并修掉 4 个真实缺陷。

| 项 | 数值 / 结果 | 来源 |
|---|---|---|
| 离线全链路 | 5 合成帧 → 5 条战术 → 入库 5 条 → 清理成功，残留 0 文件 | `python video_learner.py --synthetic 5 --game space_invaders` |
| 去重（修复前） | 同一条战术重复入库仍保留（"去重后 1 条"） | 实测，见 §2 D6 |
| 去重（修复后） | 正确剔除（"去重后 0 条"） | 同上 |
| 短中文战术（修复前） | "战术一" 被静默丢弃 | 实测，见 §2 D5 |
| 短中文战术（修复后） | 保留 | 同上 |
| 测试用例 | **862 全绿**（835 + 27 新增） | `pytest tests/ -q` |
| 门禁 | `bash scripts/check.sh` 退出码 0 | 见 §5 |

## 2. 修的四个真实缺陷

### D4 · 入库不分区 → "学 → 检索"断链（严重，跨阶段）

S15/S18 之后主循环检索的是 `knowledge_md/<game>/`，而 `save_tactics_to_kb` 仍一律写
`knowledge_md/` 根目录。**视频学到的战术永远检索不到** —— 学习链路跑得再完整，产出也进不了
决策。这是 S18 修好读取分区后暴露的下一环。现按激活游戏（或 `--game`）分区入库，
并新增跨阶段用例 `test_learned_tactics_are_retrievable` 锁死该契约。

### D5 · 短中文战术被静默丢弃（中）

`_useful()` 要求 `len(t) > 4`。中文战术天然简练，"别恋战""先撤退"这类 3 字有效条目会被
判为无意义而丢弃，且不打印任何提示。阈值改为 `len(t.strip()) >= 2`。

### D6 · 去重形同虚设（中）

`_dedup_new` 把**单条战术**与**整个历史文件 blob** 直接做 `SequenceMatcher` 比对。两者长度
差一个数量级，ratio 天然只有 0.1~0.3，阈值 0.75 **永远触发不了** —— 实测同一条战术重复入库
仍然保留。现改为从历史文件解析出逐条战术、逐条比对取最大相似度。

### D7 · 清理结果不可断言 + 帧目录不可重定向（中）

`cleanup_temp_frames()` 原无返回值，"小硬盘友好"这条原则只能靠人眼看日志验证；
`FRAME_DIR` 是写死常量，测试只能在真实仓库目录里造帧。现 `cleanup_temp_frames()` 返回 bool、
`set_frame_dir()` 可重定向、`_write_png()` 自动建父目录。

## 3. 新增能力

| 能力 | 说明 |
|---|---|
| `synthesize_frames(n)` | 纯标准库 PNG 生成器（`zlib` + `struct`，无 cv2 / 无 PIL / 无下载），每帧颜色不同以暴露逐帧逻辑缺陷 |
| `extract_frames_offline(n)` | 离线抽帧入口，无 cv2 时替代真实抽帧 |
| `set_vlm_provider(fn)` / `vlm_extract_tactic(..., provider=)` | VLM 可注入；内置 `_stub_vlm` 产出结构化战术 |
| `learn_from_video(...)` | 一次完整学习，返回 `{frames, tactics, kept, kb_file, cleaned, residual}`，可供门禁断言 |
| `_kb_target_dir(game)` | 入库分区（与 knowledge_loop 同口径） |
| CLI `--synthetic N` / `--game NAME` / `--keep-frames` | 离线跑通全链路；清理不干净时退出码 1 |

真实抽帧路径（`extract_frames`）保持原样，仅在有 cv2 且视频存在时启用，离线自动降级。

## 4. 验收记录

```
$ python video_learner.py --synthetic 5 --game space_invaders
[离线] 合成帧 5 张，VLM 走内置 stub，入库分区: space_invaders
[offline] 使用合成帧替代真实抽帧（5 帧，不依赖 cv2 / 网络）
已保存 5 条新战术到知识库: space_invaders/video_tactic_synthetic_5frames_20260922_054806.md
[离线] 抽帧 5 张 → 解析 5 条 → 入库 5 条 → 清理 成功（残留 0 个文件）
EXIT=0

$ python -m pytest tests/test_video_learner.py -q      27 passed
$ python -m pytest tests/ -q                           862 passed
$ bash scripts/check.sh                                ✅ 全部门禁通过
```

## 5. 遗留

1. **真实 VLM 与真实抽帧仍未实测**：本机无 cv2、无密钥，`extract_frames` 的 cv2 分支与
   `_default_vlm` 的 HTTP 分支只能靠代码审查。需在具备条件的机器上补一次真机验证。
2. **去重阈值 0.75 未针对中文调优**：修复后能正确剔除完全重复项，但近义不同措辞
   （"立即撤退" vs "马上撤"）仍会重复入库，需要引入语义相似度（S20 之后考虑）。
3. `video_sources.search_videos` 依赖 yt-dlp 与联网，本阶段未改造（无网络不可验证），
   仍走 download 失败提示分支。

## 6. 经验

1. **上游修好后，下游的"看起来正常"会立刻变成真缺陷**。D4 在 S18 之前不是问题（大家都读根目录），
   S18 一分片，视频学到的战术就再也找不到了。跨阶段契约要用**跨阶段用例**锁死，
   而不是各阶段各自验收。
2. **相似度去重必须保证比较对象同量级**。拿 20 字去比 5000 字，任何阈值都是摆设。
   写这类逻辑时先问："最相似的情况下 ratio 能到多少？"
3. **长度阈值要考虑语言**。英文战术动辄 40+ 字符，中文 4 字就能表达完整意图，
   直接沿用字符数阈值等于系统性丢弃中文内容。
4. **"清理"要有返回值**。没有返回值的清理函数，等于把唯一能被自动验证的环节
   降级成了人工观察项。
