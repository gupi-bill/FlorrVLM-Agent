# S25 · 文档体系重写

> 日期：2026-09-25 ｜ 状态：✅ 完成
> 目标：让陌生人 3 分钟知道这是什么、30 分钟接入一款游戏。

## 交付物与改动

| 文件 | 改动 |
|------|------|
| `README.md` | 门禁口径 6→**7 环节**（补「MCP 安装契约」）；实测用例 **920→987** |
| `docs/FAQ.md` | 新增「环境 / 本机踩坑」章节（无 X server / 无密钥 / TMPDIR / 模式查询 / 跨平台打包） |
| `PROJECT_SUMMARY.md` / `ROADMAP.md` | 已在早前统一为 987 用例 / 30 文件 |

## 验收

- 文档中命令均可复制执行（`bash scripts/check.sh`、`python launcher.py --dry-run --mock`、`python agent_cli.py -c mode`、`python tools/build_dist.py all` 均已实测）。
- `tests/test_docs.py` 文档—代码一致性门禁：**38 passed**。
- 无与实测冲突的陈述（交叉核对 S1~S24 报告）。
