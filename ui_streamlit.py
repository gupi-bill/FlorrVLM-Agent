import streamlit as st
import subprocess
import os
import yaml
from pathlib import Path

st.set_page_config(page_title="Universal Game Framework", page_icon="🎮", layout="wide")
st.title("🎮 Universal Game Framework Control Panel")
st.caption("跨平台游戏智能体控制中心")

if "log_history" not in st.session_state:
    st.session_state.log_history = []
if "current_game" not in st.session_state:
    st.session_state.current_game = "florr"

with st.sidebar:
    st.header("📁 游戏配置")
    game_profiles_dir = Path("game_profiles")
    if game_profiles_dir.exists():
        game_names = sorted([f.stem for f in game_profiles_dir.glob("*.yaml")])
    else:
        game_names = ["florr"]
    selected_game = st.selectbox("选择游戏", options=game_names, index=0)
    st.session_state.current_game = selected_game

    st.divider()
    st.subheader("📋 游戏配置快照")
    profile_path = Path(f"game_profiles/{selected_game}.yaml")
    if profile_path.exists():
        with open(profile_path) as f:
            cfg = yaml.safe_load(f)
        with st.expander("查看配置细节", expanded=False):
            st.json(cfg, expanded=False)
    else:
        st.info("配置文件不存在")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🔍 实体检测")
    if st.button("启动检测", use_container_width=True, type="primary"):
        with st.spinner("正在初始化 YOLO 检测器..."):
            try:
                result = subprocess.run(
                    ["python3", "agent_cli.py", "-c", "detect"],
                    capture_output=True, text=True, timeout=30
                )
                output = result.stdout + result.stderr
                st.session_state.log_history.append(f"[检测] {selected_game}: {output[-200:]}")
                if "player" in output.lower():
                    st.success("✅ 检测完成 - 发现玩家实体")
                elif "error" in output.lower():
                    st.error("❌ 检测出错")
                else:
                    st.info("⚠️ 检测完成 - 请查看日志详情")
            except subprocess.TimeoutExpired:
                st.error("⏰ 检测超时")
            except Exception as e:
                st.error(f"❌ 运行错误: {str(e)}")
    st.caption("使用 YOLO 扫描游戏窗口实体")

with col2:
    st.subheader("🚀 自动学习")
    search_query = st.text_input("搜索关键词", placeholder="例如：space invaders strategy")
    if st.button("启动学习", use_container_width=True, type="secondary"):
        if not search_query:
            st.warning("请输入搜索关键词")
        else:
            with st.spinner(f"正在搜索并学习: {search_query}..."):
                try:
                    result = subprocess.run(
                        ["python3", "agent_cli.py", "--auto", "search", selected_game, search_query],
                        capture_output=True, text=True, timeout=60
                    )
                    output = result.stdout + result.stderr
                    st.session_state.log_history.append(f"[学习] {selected_game}: {output[-300:]}")
                    if "knowledge" in output.lower() or "saved" in output.lower():
                        st.success("✅ 学习完成 - 写入知识库")
                    if "error" in output.lower():
                        st.error("❌ 学习过程出现错误")
                except subprocess.TimeoutExpired:
                    st.error("⏰ 搜索超时")
                except Exception as e:
                    st.error(f"❌ 运行错误: {str(e)}")
    st.caption("自动搜索教程视频 → VLM 逐帧分析 → 写入知识库")

with col3:
    st.subheader("📚 知识库")
    if st.button("刷新知识库", use_container_width=True):
        kb_dir = Path(f"knowledge_md/{selected_game}")
        if kb_dir.exists():
            files = sorted(kb_dir.glob("*.md"))
            if files:
                st.success(f"✅ {selected_game} 知识库共有 {len(files)} 条记录")
                for f in files[-5:]:
                    st.text(f"• {f.name}")
            else:
                st.warning("该游戏暂无知识库条目")
        else:
            kb_root = Path("knowledge_md")
            if kb_root.exists():
                all_md = list(kb_root.rglob("*.md"))
                st.info(f"知识库根目录共有 {len(all_md)} 个 md 文件")
            else:
                st.info("知识库目录不存在")
    try:
        kb_root = Path("knowledge_md")
        if kb_root.exists():
            total_files = len(list(kb_root.rglob("*.md")))
            st.caption(f"📊 知识库总计: {total_files} 个 Markdown 文件")
    except:
        pass

st.divider()
st.subheader("📝 实时日志输出")
recent_logs = st.session_state.log_history[-50:] if st.session_state.log_history else ["等待开始..."]
for log in recent_logs:
    st.text(log)

st.divider()
st.caption("快捷操作")
col_a, col_b = st.columns(2)
with col_a:
    if st.button("🔄 刷新状态"):
        st.rerun()
with col_b:
    if st.button("🗑️ 清空日志"):
        st.session_state.log_history = []
        st.rerun()

st.divider()
st.markdown("<div style='text-align: center; color: #666; font-size: 0.8rem;'>Universal Game Framework v2.0</div>", unsafe_allow_html=True)
