# -*- coding: utf-8 -*-
"""检查界面里是否存在重复的按钮/文字：遍历真实控件树逐级打印。

用法： python tests/inspect_widgets.py [--dark]
"""
from __future__ import annotations

import sys
import tkinter as tk
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from daily_task.history import HistoryStore  # noqa: E402
from daily_task.settings import Settings  # noqa: E402
from daily_task.ui import TaskApp  # noqa: E402
from tests.hold_window import demo_store, make_sample_history  # noqa: E402

WORK = BASE / ".build" / "inspect-data"


def walk(widget: tk.Misc, depth: int = 0, out: list | None = None) -> list:
    out = [] if out is None else out
    try:
        cls = widget.winfo_class()
        text = ""
        try:
            text = str(widget.cget("text"))
        except Exception:
            pass
        mgr = widget.winfo_manager()
        out.append((depth, cls, text, mgr, widget.winfo_x(), widget.winfo_y(),
                    widget.winfo_width(), widget.winfo_height()))
    except Exception:
        return out
    for child in widget.winfo_children():
        walk(child, depth + 1, out)
    return out


def main() -> int:
    dark = "--dark" in sys.argv
    store = demo_store(WORK)
    settings = Settings.load(WORK)
    settings.windows_toast = False
    settings.sound = False
    settings.dark_mode = dark
    settings.autostart = False
    settings.save()
    history = HistoryStore(WORK)
    history.load()
    make_sample_history(history)

    root = tk.Tk()
    app = TaskApp(root, store, settings, silent_start=False, history=history)
    app._startup_report()
    root.update()

    rows = walk(root)
    print(f"控件总数：{len(rows)}　（深色：{dark}）")
    print("\n--- 顶层结构（前 2 层）---")
    for depth, cls, text, mgr, x, y, w, h in rows:
        if depth <= 2:
            preview = text.replace("\n", "⏎")[:40]
            print(f"{'  ' * depth}{cls:<12} mgr={mgr:<6} pos=({x},{y}) size={w}x{h} text=[{preview}]")

    # 关键：统计重复文字
    texts = [t for _d, _c, t, _m, *_ in rows if t]
    duplicates = {t: n for t, n in Counter(texts).items() if n > 1}
    print("\n--- 重复的文字 ---")
    if duplicates:
        for text, count in duplicates.items():
            print(f"  ×{count}  {text.replace(chr(10), '⏎')[:60]}")
    else:
        print("  无")

    for keyword in ("＋ 新建任务", "每日任务提醒", "今日打卡", "完成记录", "系统 ▾"):
        count = sum(1 for t in texts if t == keyword)
        print(f"  「{keyword}」出现次数：{count}")
        assert count <= 1, f"「{keyword}」在控件树里出现了 {count} 次，界面确实重复了"

    assert len(rows) < 60, f"控件数量异常偏多：{len(rows)}"
    print("\n[OK] 控件树中没有重复的按钮或文字")
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
