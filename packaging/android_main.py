#!/usr/bin/env python3
"""
FlorrVLM-Agent  Android 壳入口  (v1.9)
实验性最小 APK：能在手机打开，展示本包信息。
完整智能体核心跑在桌面，需再接网络把状态推到此壳（见 README）。
"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.clock import Clock


class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        self.add_widget(Label(text="FlorrVLM-Agent v1.9", font_size=28, bold=True))
        self.add_widget(Label(
            text="通用游戏操作引擎 · 哦带了壳版\n\n"
                 "核心(桌面)功能：VLM 视觉感知 / 实体预判 / 战斗评估 / MCP 知识库\n\n"
                 "此 APK 为手机展示壳，真实 agent 跑在电脑。\n"
                 "若需手游自动操作，需另接键盘/模拟器驱动。",
            font_size=16))

    def on_touch_down(self, touch):
        import os
        labels = self.children[0]
        labels.text += f"\n\t一次点击 @{int(touch.x)},{int(touch.y)}"
        return True


class FlorrApp(App):
    def build(self):
        self.root = Root()
        return self.root


if __name__ == "__main__":
    FlorrApp().run()