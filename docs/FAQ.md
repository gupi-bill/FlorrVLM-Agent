# 常见问题（FAQ）

> 面向「把它装到自己 Agent 上」的人。装之前先看 [MCP_INSTALL.md](./MCP_INSTALL.md)。

## 装不上 / 客户端看不见工具

**Q：`install_mcp.py --list` 里所有目标都是「配置文件不存在」？**
A：正常。脚本只往**已存在**的客户端配置里合并，不会凭空造文件。
用 `--target custom --path /绝对路径/mcp.json` 指定你自己的配置文件，
或者先在客户端里随便加一个 MCP 服务让它生成配置文件，再跑脚本。

**Q：装完了，客户端里还是看不到 `ugf`？**
A：三件事依次确认：
1. `python tools/install_mcp.py --list` 里对应目标是否显示「✅ 已注册 ugf」；
2. 客户端的「连接器 / MCP 设置」页里有没有把 `ugf` 设为**信任**（新服务默认不信任）；
3. 重启客户端——大多数客户端只在启动时拉起 MCP 服务。

**Q：有没有一步到位看出卡在哪的办法？**
A：有，`python tools/install_mcp.py --check`：查入口文件、解释器、依赖，并真实拉起服务做一次握手，
最后打印实际拿到的工具数量。

**Q：服务起来了，但报 `ModuleNotFoundError`？**
A：配置里的 `command` 必须是**装了依赖的那个 Python**。用 `tools/install_mcp.py` 自动写入时
它会填当前 `sys.executable`（也就是你正在用的 venv）；手写配置时别忘了换成绝对路径。

**Q：想卸载？**
A：`python tools/install_mcp.py --target <名字> --remove`（只删 ugf 那一条，不动其它服务）。

---

## 传输与并发

**Q：stdio 和 streamable-http 该选哪个？**
A：单客户端用 stdio（默认，最省事）；多个客户端同时接就起 HTTP：
`python mcp_server.py --transport streamable-http --port 5050`，客户端填 `http://127.0.0.1:5050/mcp`。

**Q：能不能让别的机器也连？**
A：可以，但**务必先加鉴权或只在内网监听**。HTTP 模式默认只监听 `127.0.0.1`，
一旦改成 `0.0.0.0`，任何能访问该端口的人都能驱动你的键鼠。

---

## dry-run 与真实操作

**Q：为什么我调 `game_action` 画面没反应？**
A：默认开着 dry-run（`UGF_DRY_RUN=1`），只校验参数并返回描述，不动键鼠。
这是刻意的：先联调，确认接线无误再放开。
要在授权环境里放开：装的时候加 `--online`，或设环境变量 `UGF_DRY_RUN=0`。

**Q：dry-run 下做过什么动作能查吗？**
A：能，动作会落到 `run_logs/dryrun_actions.log`，便于回放核对。

**Q：没有 YOLO / 感知服务会怎样？**
A：`perceive_game` 会降级为进程内合成帧，返回值里带 `_fallback` 标记，整条链路照样跑通。
这是为了让你先联调再上真机——但别把 mock 数据当战绩。

---

## 预判与知识库

**Q：`predict_all_entities` 返回 `insufficient_data`？**
A：历史帧不足 3 帧。连续多调几次 `perceive_game` 再预判。

**Q：预判结果里 `x_predict` 是 null？**
A：`confidence < 0.65` 时 `prediction_trusted=false`，坐标不输出。低置信就别信，按当前坐标决策。

**Q：我传的文件名里有 `..`，结果写到别处了吗？**
A：没有。路径会被清洗回知识库目录内，返回文本里会显示**实际写入路径**，照着看即可。

**Q：知识库怎么备份 / 迁移？**
A：`kb_export` 打包成 tar.gz，`kb_import` 恢复。

---

## 合规

**Q：能拿去玩在线游戏吗？**
A：不能。本能力包面向本地 / 自建 / 已授权的靶场环境。
在他人运营的在线服务器上跑自动化程序违反其服务条款，框架不提供任何绕过手段。
