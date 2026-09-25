# S23 · 安全与合规加固

> 日期：2026-09-25 ｜ 状态：✅ 完成
> 目标：框架要能被别人放心使用与分发。

## 交付物

| 文件 | 说明 |
|------|------|
| `tests/test_security.py` | 22 项离线安全测试（穿越/密钥/沙箱/合规） |
| `game_profile_check.py` | 修复：档案路径穿越缺陷（新增 `_safe_profile_name` + `commonpath` 二次守门） |
| 本报告 | 加固清单与验证记录 |

## 本轮发现并修复的真实缺陷

档案加载路径穿越（`game_profile_check._profile_path`）

- 现象：`_profile_path("../../etc/passwd")` → `game_profiles/../../etc/passwd.yaml`，逃出档案目录，可被诱读项目外任意 `.yaml`。
- 修复：新增 `_safe_profile_name()`（只保留末段、去 `..`），并加 `commonpath` 二次守门；归一化后越界则回退 `__invalid__.yaml`。
- 验证：9 种穿越名全部限定在 `game_profiles/` 内；正常名（florr/space_invaders/_template/demo_arcade）不受影响；`test_game_profiles.py` 38 passed。

## 复核结论（已有防线，本轮加测试锁死）

1. 知识库读写（`mcp_server._safe_name`）：文件名/游戏名/战术名去分隔符与 `..`，`commonpath` 守门——已有（S9）。
2. 备份导入（`kb_maintainer.import_backup`）：tar 成员名过滤 + `commonpath` 二次守门——已有（S9）。
3. 档案 YAML 解析：`yaml.safe_load` 拒绝 python tag 等恶意 tag，返回可读错误而非 traceback——已有。
4. 密钥：`.gitignore` 排除 `.env`；文档/示例无真实密钥字面量——已有，本轮加扫描测试。
5. 合规声明：README / PROJECT_SUMMARY 含「本地/授权环境」提醒——已有（S2/S3），本轮加测试锁死。

## 验收

- `tests/test_security.py`：22 passed。
- 恶意档案（python tag / 超大数值 / 错误类型 / 空）全部返回可读错误，零崩溃。
- 全仓测试：987 用例（30 文件）。

## 说明

- GitHub Actions 依赖漏洞扫描（Dependabot/CodeQL）为云端配置项，本地无法实证，列入后续。
- 渗透测试 MCP HTTP 端口需真实网络环境，本环境为离线，列入后续。
