#!/usr/bin/env python3
"""Universal Game Framework - Tkinter Desktop GUI

一个基于 Tkinter 的桌面图形界面，提供：
1. 游戏选择下拉框
2. 实体检测按钮
3. 自动学习功能
4. 知识库浏览和管理
5. 实时日志输出
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import subprocess
import os
import sys
import yaml
from pathlib import Path
import shutil


class GameFrameworkUI:
    """主应用类"""

    def __init__(self, root):
        self.root = root
        self.root.title("Universal Game Framework - Control Panel")
        self.root.geometry("900×600")
        self.root.minsize(800, 500)

        # 状态变量
        self.current_game = tk.StringVar(value="florr")
        self.log_messages = []
        self.max_log_lines = 100

        # 初始化 UI
        self._create_widgets()
        _scan_and_set_game()
        # 确保知识库目录存在
        self._ensure_directories()

    def _ensure_directories(self):
        """确保必需目录存在"""
        for d in ["game_profiles", "knowledge_md", "run_logs"]:
            Path(d).mkdir(parents=True, exist_ok=True)

    def _create_widgets(self):
        """创建所有 UI 组件"""

        # ===== 顶部：游戏选择区 =====
        top_frame = ttk.LabelFrame(self.root, text="📁 游戏配置", padding=(10, 5))
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        # 游戏下拉选择
        ttk.Label(top_frame, text="目标游戏:").pack(side=tk.LEFT)

        # 自动扫描 game_profiles
        game_names = self._scan_game_profiles()
        self.game_combo = ttk.Combobox(
            top_frame,
            textvariable=self.current_game,
            values=game_names,
            state="readonly",
            width=20
        )
        self.game_combo.pack(side=tk.LEFT, padx=(10, 0))
        if game_names:
            self.game_combo.current(0)
        self.game_combo.bind("<<ComboboxSelected>>", self._on_game_change)

        # 刷新按钮
        ttk.Button(top_frame, text="↻", width=2,
                   command=self._refresh_games).pack(side=tk.RIGHT, padx=5)

        # ===== 中部：核心功能区 =====
        mid_frame = ttk.LabelFrame(self.root, text="🎯 核心功能", padding=(10, 5))
        mid_frame.pack(fill=tk.X, padx=10, pady=5)

        # 三个按钮列
        btn_frame = tk.Frame(mid_frame)
        btn_frame.pack(fill=tk.X)

        # 检测按钮
        self.btn_detect = ttk.Button(
            btn_frame,
            text="🔍 检测实体",
            command=self._on_detect,
            state=tk.NORMAL
        )
        self.btn_detect.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        # 自动学习按钮
        self.btn_learn = ttk.Button(
            btn_frame,
            text="🚀 自动学习",
            command=self._on_auto_learn,
            state=tk.NORMAL
        )
        self.btn_learn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 5))

        # 知识库按钮
        self.btn_kb = ttk.Button(
            btn_frame,
            text="📚 知识库",
            command=self._on_knowledge_base,
            state=tk.NORMAL
        )
        self.btn_kb.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

        # ===== 下部：日志与状态区 =====
        bottom_frame = ttk.Frame(self.root, padding=(10, 5))
        bottom_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 日志区域
        ttk.Label(bottom_frame, text="📝 运行日志:").pack(anchor=tk.W)
        self.log_area = scrolledtext.ScrolledText(
            bottom_frame,
            height=15,
            bg="#1e1e1e",
            fg="#d4d4d4",
            font="Consolas 9",
            state=tk.DISABLED
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        # 控制按钮栏
        control_frame = ttk.Frame(bottom_frame)
        control_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(control_frame, text="🗑️ 清空日志",
                   command=self._clear_logs).pack(side=tk.RIGHT)
        ttk.Button(control_frame, text="📋 复制日志",
                   command=self._copy_log).pack(side=tk.RIGHT, padx=(0, 5))

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _scan_game_profiles(self):
        """扫描 game_profiles 目录返回游戏名称列表"""
        profiles_dir = Path("game_profiles")
        if profiles_dir.exists():
            names = sorted([f.stem for f in profiles_dir.glob("*.yaml")])
            # 确保 florr 始终在列表中（向后兼容）
            if "florr" not in names and names:
                names.insert(0, "florr")
            return names
        return ["florr", "space_invaders"]

    def _refresh_games(self):
        """刷新游戏列表"""
        games = self._scan_game_profiles()
        if games != self.game_combo['values']:
            self.game_combo['values'] = games
            if self.current_game.get() not in games:
                self.current_game.set(games[0] if games else "florr")
        self._append_log(f"✅ 游戏列表已刷新: {len(games)} 款游戏")

    def _on_game_change(self, event=None):
        """游戏选择改变时的回调"""
        game = self.current_game.get()
        self._append_log(f"🔄 切换到游戏: {game}")
        self.status_var.set(f"当前游戏: {game}")
        # 这里可以重新加载该游戏的配置参数

    def _append_log(self, message):
        """添加日志消息"""
        self.log_messages.append(message)
        # 保持日志行数在限制内
        if len(self.log_messages) > self.max_log_lines:
            self.log_messages = self.log_messages[-self.max_log_lines:]

        # 更新显示区
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)  # 自动滚动到底部
        self.log_area.config(state=tk.DISABLED)

    def _clear_logs(self):
        """清空日志"""
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=tk.DISABLED)
        self.log_messages = []
        self._append_log("🗑️ 日志已清空")

    def _copy_log(self):
        """复制日志到剪贴板"""
        try:
            content = self.log_area.get(1.0, tk.END)
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self._append_log("📋 日志已复制到剪贴板")
        except Exception as e:
            self._append_log(f"❌ 复制失败: {e}")

    # ===== 功能事件处理 =====

    def _on_detect(self):
        """处理实体检测按钮点击"""
        game = self.current_game.get()
        self._append_log(f"▶️ 启动实体检测: {game}")
        self.status_var.set(f"检测中... ({game})")

        try:
            result = subprocess.run(
                ["python3", "agent_cli.py", "-c", "detect"],
                capture_output=True,
                text=True,
                timeout=45
            )
            output = result.stdout + result.stderr
            # 关键结果提示
            if "player" in output.lower():
                self._append_log("✅ 检测成功 - 发现玩家实体")
            elif "error" in output.lower():
                self._append_log("❌ 检测出错")
            else:
                self._append_log("⚠️ 检测完成 - 详见日志")

            # 显示关键输出片段
            snippet = output[-300:] if len(output) > 300 else output
            self._append_log(f"输出片段: {snippet}")

        except subprocess.TimeoutExpired:
            self._append_log("⏰ 检测超时 - 可能未检测到游戏窗口")
        except FileNotFoundError:
            self._append_log("❌ 未找到 agent_cli.py，请检查路径")
        except Exception as e:
            self._append_log(f"❌ 运行异常: {str(e)}")
        finally:
            self.status_var.set(f"就绪 - {game}")

    def _on_auto_learn(self):
        """处理自动学习按钮"""
        game = self.current_game.get()
        query = st_input_dialog(game) if False else ""
        
        # 弹出输入框询问搜索关键词
        keyword = tk.simpledialog.askstring(
            "搜索关键词",
            f"请输入要搜索的关键词（针对 {game}）：\n"
            "例如：'basic tutorial', 'boss strategy', 'opening guide'\n\n"
            "留空将使用默认关键词 'basic guide'",
            initialvalue="basic guide"
        )
        
        if not keyword:
            keyword = "basic guide"
        
        if keyword.strip():
            self._append_log(f"▶️ 启动自动学习: {game} | 关键词: {keyword}")
            self.status_var.set(f"学习中... ({game})")

            try:
                result = subprocess.run(
                    ["python3", "agent_cli.py", "--auto", "search", game, keyword],
                    capture_output=True,
                    text=True,
                    timeout=90
                )
                output = result.stdout + result.stderr
                snippet = output[-400:] if len(output) > 400 else output
                
                # 判断结果
                if "knowledge" in output.lower() or "saved" in output.lower():
                    self._append_log("✅ 学习完成 - 已写入知识库")
                    # 尝试列出新增的文件
                    self._refresh_knowledge_list()
                elif result.returncode != 0:
                    self._append_log(f"⚠️ 学习结束 - 返回码: {result.returncode}")
                    self._append_log(f"输出: {snippet[:200]}")
                else:
                    self._append_log("ℹ️ 学习过程已完成")
                    self._append_log(f"详情: {snippet[:300]}")

            except subprocess.TimeoutExpired:
                self._append_log("⏰ 搜索超时 - 请尝试简化关键词或检查网络")
            except FileNotFoundError:
                self._append_log("❌ 未找到 agent_cli.py")
            except Exception as e:
                self._append_log(f"❌ 学习过程出错: {str(e)}")
            finally:
                self.status_var.set(f"就绪 - {game}")
        else:
            self._append_log("ℹ️ 已取消学习操作")

    def st_input_dialog(game):
        """伪函数占位 - 实际 Streamlit 有自己的输入框"""
        return "basic guide"

    def _on_knowledge_base(self):
        """处理知识库按钮点击"""
        game = self.current_game.get()
        kb_dir = Path(f"knowledge_md/{game}")

        if not kb_dir.exists():
            # 尝试查找任何知识库
            kb_root = Path("knowledge_md")
            if kb_root.exists() and any(kb_root.rglob("*.md")):
                kb_dir = kb_root  # 显示所有
            else:
                messagebox.showinfo(
                    "知识库",
                    f"游戏 {game} 的知识库不存在。\n\n"
                    "点击「自动学习」将在首次学习后创建。"
                )
                return

        # 统计文件
        md_files = sorted(kb_dir.glob("*.md"))
        total = len(md_files)

        # 显示统计信息
        info_parts = [f"游戏: {game}", f"知识库文件: {total} 个"]
        
        # 如果文件较少，列出细节
        if total > 0 and total <= 50:
            details = ["\n最近条目:"]
            for f in md_files[-10:]:  # 最近10个
                details.append(f"  • {f.name}")
            info_parts.append("\n".join(details))
        elif total > 50:
            info_parts.append(f"\n... 共 {total} 条记录 (仅显示最近10个)")
            details = ["\n最近条目:"]
            for f in md_files[-10:]:
                details.append(f"  • {f.name}")
            info_parts.append("\n".join(details))

        # 显示信息框
        message = "\n".join(info_parts)
        messagebox.showinfo(f"知识库 - {game}", info_msg)

    def _refresh_knowledge_list(self):
        """刷新知识库文件列表"""
        game = self.current_game.get()
        kb_dir = Path(f"knowledge_md/{game}")
        if kb_dir.exists():
            files = sorted(kb_dir.glob("*.md"))
            count = len(files)
            self._append_log(f"📚 {game} 知识库当前有 {count} 条记录")
        else:
            kb_root = Path("knowledge_md")
            if kb_root.exists():
                all_files = list(kb_root.rglob("*.md"))
                self._append_log(f"📚 知识库根目录共有 {len(all_files)} 个 md 文件")


def main():
    """入口函数"""
    root = tk.Tk()
    
    # 设置窗口图标（如果有的话）
    try:
        # 尝试设置窗口图标
        icon_path = Path("ui_icon.ico")
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
    except Exception:
        pass
    
    app = GameFrameworkUI(root)
    
    # 处理关闭窗口
    def on_closing():
        if messagebox.askokcancel("退出", "确定要退出 Universal Game Framework 吗？"):
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    print("=" * 60)
    print("Universal Game Framework - Desktop GUI")
    print("Starting Streamlit-style control panel in Tkinter...")
    print("=" * 60)
    print()
    print("可用功能:")
    print("  1. 游戏选择 - 从 game_profiles 目录自动扫描")
    print("  2. 实体检测 - YOLO 检测游戏窗口实体")
    print("  3. 自动学习 - VLM 搜索 + 知识库写入")
    print("  4. 知识库管理 - 浏览/搜索/清空")
    print("  5. 实时日志 - 完整运行日志追踪")
    print()
    print("快捷键:")
    print("  Esc - 关闭应用确认")
    print("=" * 60)
    
    root = tk.Tk()
    app = GameFrameworkUI(root)
    root.mainloop()