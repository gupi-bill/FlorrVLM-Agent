#!/usr/bin/env python3
"""
⚠ DEPRECATED（S11 归档）：PyQt 桌面面板已不再是主 UI。
主 UI = admin_panel.py（纯标准库，无重依赖）；离线备选 = ui_tkinter.py。
统一入口：`python launcher.py --ui auto`（可用 --ui pyqt 强制拉起本文件）。
仅接受缺陷修复，不再新增功能。
"""
import os
import sys

# S11 归档到 ui/legacy/ 后，项目根目录不在 sys.path 里，这里补回
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

"""Universal Game Framework - PyQt6 Desktop GUI"""

import sys
import os
import subprocess
import yaml
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTextEdit, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor


class WorkerThread(QThread):
    """后台执行命令的线程"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, cmd_list, timeout=60):
        super().__init__()
        self.cmd_list = cmd_list
        self.timeout = timeout

    def run(self):
        try:
            result = subprocess.run(
                self.cmd_list,
                capture_output=True, text=True, timeout=self.timeout
            )
            output = result.stdout + result.stderr
            self.finished.emit(output)
        except subprocess.TimeoutExpired:
            self.error.emit("⏰ 操作超时")
        except Exception as e:
            self.error.emit(f"❌ 错误: {str(e)}")


class GameFrameworkUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Universal Game Framework - Control Panel")
        self.setGeometry(100, 100, 900, 600)
        self.current_game = "florr"

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 游戏选择区
        game_group = QGroupBox("📁 游戏配置")
        game_layout = QHBoxLayout()
        game_layout.addWidget(QLabel("目标游戏:"))
        self.game_combo = QComboBox()
        self.game_combo.currentTextChanged.connect(self.on_game_change)
        game_layout.addWidget(self.game_combo)
        refresh_btn = QPushButton("↻ 刷新")
        refresh_btn.clicked.connect(self.refresh_games)
        game_layout.addWidget(refresh_btn)
        game_group.setLayout(game_layout)
        main_layout.addWidget(game_group)

        # 功能按钮区
        btn_group = QGroupBox("🎯 核心功能")
        btn_layout = QHBoxLayout()

        detect_btn = QPushButton("🔍 检测实体")
        detect_btn.clicked.connect(self.on_detect)
        btn_layout.addWidget(detect_btn)

        learn_btn = QPushButton("🚀 自动学习")
        learn_btn.clicked.connect(self.on_learn)
        btn_layout.addWidget(learn_btn)

        kb_btn = QPushButton("📚 知识库")
        kb_btn.clicked.connect(self.on_knowledge)
        btn_layout.addWidget(kb_btn)

        btn_group.setLayout(btn_layout)
        main_layout.addWidget(btn_group)

        # 日志区
        log_group = QGroupBox("📝 运行日志")
        log_layout = QVBoxLayout()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Consolas", 9))
        self.log_area.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        log_layout.addWidget(self.log_area)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        # 清空按钮
        clear_btn = QPushButton("🗑️ 清空日志")
        clear_btn.clicked.connect(self.clear_logs)
        main_layout.addWidget(clear_btn)

        self.refresh_games()

    def refresh_games(self):
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        profiles_dir = Path("game_profiles")
        if profiles_dir.exists():
            games = sorted([f.stem for f in profiles_dir.glob("*.yaml")])
        else:
            games = ["florr"]
        self.game_combo.addItems(games)
        self.game_combo.blockSignals(False)
        self.append_log(f"✅ 游戏列表已刷新: {len(games)} 款游戏")

    def on_game_change(self, game):
        if game:
            self.current_game = game
            self.append_log(f"🔄 切换到游戏: {game}")

    def append_log(self, msg):
        self.log_area.append(msg)
        self.log_area.moveCursor(QTextCursor.MoveOperation.End)

    def clear_logs(self):
        self.log_area.clear()
        self.append_log("🗑️ 日志已清空")

    def on_detect(self):
        game = self.current_game
        self.append_log(f"▶️ 启动实体检测: {game}")
        self.worker = WorkerThread([sys.executable, "agent_cli.py", "-c", "detect"], timeout=30)
        self.worker.finished.connect(lambda out: self.append_log(f"✅ 检测完成\n{out[-300:]}"))
        self.worker.error.connect(lambda err: self.append_log(err))
        self.worker.start()

    def on_learn(self):
        game = self.current_game
        self.append_log(f"▶️ 启动自动学习: {game}")
        self.worker = WorkerThread(
            [sys.executable, "agent_cli.py", "--auto", "search", game, "basic guide"], timeout=90
        )
        self.worker.finished.connect(lambda out: self.append_log(f"✅ 学习完成\n{out[-300:]}"))
        self.worker.error.connect(lambda err: self.append_log(err))
        self.worker.start()

    def on_knowledge(self):
        game = self.current_game
        kb_dir = Path(f"knowledge_md/{game}")
        if kb_dir.exists():
            files = sorted(kb_dir.glob("*.md"))
            if files:
                msg = f"📚 {game} 知识库:\n" + "\n".join(f"  • {f.name}" for f in files)
            else:
                msg = f"📚 {game} 暂无知识库条目"
        else:
            msg = f"📚 {game} 知识库目录不存在"
        self.append_log(msg)


def main():
    app = QApplication(sys.argv)
    window = GameFrameworkUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
