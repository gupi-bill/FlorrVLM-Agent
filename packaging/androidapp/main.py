#!/usr/bin/env python3
"""main.py —— Android 壳入口（buildozer 会从这里启动 Kivy）。"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label


class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        self._log = Label(text="FlorrVLM-Agent v1.9 · Android 壳\n"
                               "通用游戏操作引擎的移动端展示壳\n\n"
                               "核心(桌面)能力：VLM 视觉感知 / 实体预判 / "
                               "战斗评估 / MCP 知识库",
                          font_size=15, halign="center", valign="middle")
        self._log.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self._log)

    def on_touch_down(self, touch):
        self._log.text += f"\n\t点击@{int(touch.x)},{int(touch.y)}"
        return True


class FlorrApp(App):
    def build(self):
        return Root()


if __name__ == "__main__":
    FlorrApp().run()