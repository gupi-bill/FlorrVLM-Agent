#!/usr/bin/env python3
"""一次性脚本：把 mcp_server.py 里各 @mcp.tool 的 docstring 换成「外部模型可读」版本。

按 AST 定位 docstring 节点，行/列精确替换，不动其它代码。
"""
import ast
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "mcp_server.py")

NEW = {
    "kb_list": """列出知识库里已有的 Markdown 文档名。

用途：动手前先看本地有没有这个游戏的资料，避免重复研究。
入参：game_name 可选；给了就只列该游戏文件夹下的文档。
返回：JSON 字符串——文档名数组。
下一步：把感兴趣的文档名交给 kb_search 检索正文；没有相关资料就先 kb_write 建一份。""",

    "kb_search": """在本地 Markdown 知识库里做关键词检索。

用途：查某只怪 / 某个 BOSS / 某套战术的已知资料（语义检索优先，不可用时降级为全文匹配）。
入参：keyword 必填关键词；game_name 可选，限定在某个游戏文件夹内搜索。
返回：命中的文档片段文本；没有命中时返回空结果或提示文本。
下一步：把资料用于决策；资料缺失或过时就用 kb_write / kb_append 补上。""",

    "kb_write": """把一段 Markdown 写进知识库（不存在则新建，已存在则整体覆盖）。

用途：保存新学到的战术、怪物习性、本局结论。
入参：filename 文件名（不要带路径）；markdown_content 正文；game_name 可选，用于分类到子文件夹。
返回：成功为「已写入知识库: <路径> (N 字符)」；失败返回「错误: ...」。
注意：这是覆盖写。想追加请用 kb_append。""",

    "kb_append": """向知识库已有文档追加内容（文档不存在则自动新建）。

用途：一局结束后补一行结论、给 BOSS 习性加一条新观察。
入参：filename、markdown_content、game_name（可选，分类文件夹）。
返回：成功为「已追加到知识库: <路径>」；失败返回「错误: ...」。
下一步：配合 kb_search 复用这些累积经验。""",

    "kb_export": """把整个知识库（活跃 + 归档）打包成 tar.gz 备份。

用途：换机迁移、定期备份。
入参：无。
返回：备份文件路径或状态文本。
下一步：在新机器上用 kb_import 恢复。""",

    "kb_import": """从 kb_export 生成的 tar.gz 备份恢复知识库（同名文件覆盖）。

入参：backup_path，备份文件的绝对路径或相对项目根目录的路径。
返回：恢复结果文本（含恢复的文件数）。""",

    "perceive_game": """获取当前游戏画面状态（自身 HP、周围实体列表等），并自动喂给预判模块。

用途：每一步决策前先「看一眼」，也是 predict_all_entities 的数据来源。
入参：无。
返回：JSON 字符串——含自身状态与 entities 实体列表。需要连续调用多帧（≥3 帧）
      后续预判才有效。感知服务不可用时会自动降级为进程内合成帧，
      结果里带 _fallback 标记（离线联调照常可用，不会抛异常）。
下一步：predict_all_entities 做位置预判，或 kb_search 查资料。""",

    "predict_all_entities": """预测画面中全部实体未来约 1.2 秒的位置。

用途：判断威胁、决定走位与攻击目标。
入参：无（依赖此前多次 perceive_game 积累的历史帧）。
返回：JSON 数组，按威胁从高到低最多 8 个实体，每项含 raw_id / rarity / category /
      threat_score / x_now / y_now / x_predict / y_predict / vx_per_sec / vy_per_sec /
      confidence / prediction_trusted。confidence < 0.65 时 prediction_trusted=false
      且 x_predict、y_predict 为 null（此时不要相信预判）。
      历史帧不足时返回 {"status": "insufficient_data", ...}。
下一步：据此决定 game_action 的 move / attack。""",

    "reset_predictor": """清空预判模块的全部历史帧。

用途：新开一局、重生、或画面大幅跳变后调用，避免用旧轨迹误判。
入参：无。返回：确认文本。
下一步：重新连续调用 perceive_game 积累帧。""",

    "game_action": """执行一个游戏动作。

用途：把决策落地成实际操作。
入参：action_type 必填，取 move / attack / defend / synthesize / idle；
      move 时必须给 x、y 目标坐标（内部会做拟人化路径微扰和偶发停顿）。
      切换套装请用 switch_set，不要用本工具。
返回：动作执行结果文本。默认 dry-run（UGF_DRY_RUN=1）只校验参数并返回描述，
      不会真的动键鼠；只有在获得授权的环境里才关闭 dry-run。""",

    "switch_set": """切换当前套装 / 阵型。

入参：set_name 可传当前游戏档案 combat.sets 里的名字（例如 space_invaders 的
      shoot / dodge / focus_mothership），也可传决策层的抽象名
      （combat / tank / retreat / chase / team），后者按档案 combat.set_map 翻译。
返回：「已切换套装: <名称> (按键 N)」；dry-run 下返回
      「[dry-run] 套装切换已记录（未真实执行）」；传错名字时返回「未知套装: ...」并列出可选值。""",

    "handle_afk": """处理游戏内的 AFK 人机验证弹窗。

用途：长时间挂机触发验证时调用。
入参：无。
返回：操作指引文本。
下一步：结合 perceive_game 返回的弹窗坐标，用 game_action(move) 完成点击验证。""",

    "query_boss_history": """读取知识库里记录的 BOSS 行为习惯。

入参：boss_name 可选；不传返回全部记录，传了只返回名字匹配的记录。
返回：历史习性文本；无记录时返回「知识库还没有 BOSS 行为记录(文件不存在)。」
下一步：把习性用于决策，打完用 kb_append 补充新观察。""",

    "clean_cache": """清理运行期缓存。

入参：target 取 all（默认，清全部）/ predict（只清预判历史）/ frames（只清临时帧目录）。
返回：清理结果文本。
用途：长时间运行后释放磁盘；换局前保证预判数据干净。""",

    "switch_tactic": """指定知识库里的一份 Markdown 文件作为「当前战术」。

用途：让后续决策直接读取这份战术，不用每次重新检索。
入参：tactic_file，知识库中的文档名。
返回：「已切换当前战术为: <文件名>」；文件名非法或文档不存在时返回对应错误文本。
下一步：配合 kb_search / kb_append 迭代这份战术。""",
}


def main():
    src = open(SRC, encoding="utf-8").read()
    tree = ast.parse(src)

    targets = []
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef):
            continue
        if not any("mcp.tool" in ast.unparse(d) for d in n.decorator_list):
            continue
        if n.name not in NEW or ast.get_docstring(n) is None:
            continue
        doc_node = n.body[0]
        targets.append((doc_node.lineno - 1, doc_node.col_offset,
                        doc_node.end_lineno - 1, doc_node.end_col_offset,
                        n.name, doc_node.col_offset))

    if not targets:
        raise SystemExit("没找到任何可替换的 docstring")

    lines = src.splitlines(keepends=True)
    # 从下往上替换，避免行号漂移
    for sl, sc, el, ec, name, indent in sorted(targets, reverse=True):
        pad = " " * indent
        body = NEW[name].split("\n")
        text = pad + '"""' + body[0] + "\n"
        for ln in body[1:]:
            text += (pad + ln if ln else "") + "\n"
        text += pad + '"""'
        # 原行尾的换行符被整段替换掉了，这里补回来，否则会和下一行代码粘在一起
        text += "\n"
        lines[sl:el + 1] = [text]

    open(SRC, "w", encoding="utf-8").write("".join(lines))
    print(f"✅ 已替换 {len(targets)} 个工具描述：")
    for t in targets:
        print("   -", t[4])


if __name__ == "__main__":
    main()
