# -*- coding: utf-8 -*-
"""开发期辅助：长时间驻留的窗口实例，供窗口截图脚本使用。

用法：
    python tests/hold_window.py [--empty|--demo|--dialog|--popups|--history] [--dark]
    python tests/hold_window.py --demo --dark
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import tkinter as tk  # noqa: E402

from daily_task.history import HistoryStore  # noqa: E402
from daily_task.settings import Settings  # noqa: E402
from daily_task.tasks import Task, TaskStore  # noqa: E402
from daily_task.ui import TaskApp, TaskDialog  # noqa: E402


def demo_store(workdir: Path) -> TaskStore:
    workdir.mkdir(parents=True, exist_ok=True)
    store = TaskStore(workdir)
    now = datetime.now()
    soon = (now + timedelta(minutes=25)).strftime("%H:%M")
    store.add(Task(title="喝一杯水", kind="daily", time=soon, notes="久坐提醒，起来走两步"))
    store.add(Task(title="晚上跑步 30 分钟", kind="daily", time="20:30"))
    store.add(Task(title="工作日报", kind="daily", time="18:00", weekdays=[0, 1, 2, 3, 4]))
    store.add(Task(title="给妈妈打电话", kind="daily", time="19:30", weekdays=[6]))
    store.add(Task(title="提交季度报销单", kind="once",
                   date=(date.today() + timedelta(days=2)).strftime("%Y-%m-%d"), time="10:00",
                   notes="记得附上发票扫描件"))
    store.add(Task(title="上午 9 点例会", kind="daily", time="09:00", weekdays=[0, 1, 2, 3, 4],
                   last_done=date.today().strftime("%Y-%m-%d")))
    store.add(Task(title="整理书桌", kind="daily", time="21:00", enabled=False))
    store.save()
    return store


def make_sample_history(history: HistoryStore) -> None:
    """造一批有代表性的打卡记录：有准点、有提前、有延后。"""
    history.clear()
    samples = [
        # (几天前, 任务名, 类型, 计划时间, 实际完成相对计划的分差(分钟), 来源)
        (4, "喝一杯水", "daily", "09:00", -5, "list"),
        (4, "工作日报", "daily", "18:00", 12, "card"),
        (3, "晚上跑步 30 分钟", "daily", "20:30", -20, "card"),
        (3, "整理书桌", "daily", "21:00", 3, "list"),
        (3, "喝一杯水", "daily", "09:00", 0, "list"),
        (2, "工作日报", "daily", "18:00", 42, "list"),
        (1, "提交季度报销单", "once", "10:00", -8, "card"),
        (1, "给妈妈打电话", "daily", "19:30", 6, "list"),
        (0, "喝一杯水", "daily", "09:00", 1, "list"),
        (0, "上午 9 点例会", "daily", "09:00", 25, "card"),
    ]
    today = date.today()
    for days_ago, title, kind, planned, delta, source in samples:
        day = today - timedelta(days=days_ago)
        hour, minute = (int(x) for x in planned.split(":"))
        moment = datetime(day.year, day.month, day.day, hour, minute) + timedelta(minutes=delta)
        history.add(title=title, kind=kind, schedule=f"{planned} · 每天", source=source,
                    notes="记得打卡" if source == "list" and delta > 0 else "",
                    stamp=moment)
    history.save()


def main() -> int:
    mode = "demo"
    for flag in ("--empty", "--demo", "--dialog", "--popups", "--history"):
        if flag in sys.argv:
            mode = flag[2:]
    dark = "--dark" in sys.argv
    workdir = BASE / ".build" / ("visual-data" if mode != "empty" else "visual-empty")
    if mode == "empty" and workdir.exists():
        for item in workdir.iterdir():
            if item.is_file():
                item.unlink()
    store = demo_store(workdir) if mode != "empty" else TaskStore(workdir)
    if mode == "empty":
        store.tasks = []
    settings = Settings.load(workdir)
    settings.windows_toast = False
    settings.sound = False
    settings.dark_mode = dark
    settings.autostart = False
    settings.save()

    history = HistoryStore(workdir)
    history.load()
    if not history.records or mode == "history":
        make_sample_history(history)

    root = tk.Tk()
    app = TaskApp(root, store, settings, silent_start=False, history=history)
    root.update()
    root.after(400, lambda: root.update())      # 让 _startup_report 真正跑完
    app._startup_report()                       # 立刻填充列表，截图前就有内容
    root.update()

    def prepare() -> None:
        if mode == "dialog":
            TaskDialog(root, store.tasks[4], palette=app.palette)
        elif mode == "popups":
            app._show_alert = lambda *a, **k: None      # 不出声、不发系统通知
            for task in store.tasks[:2]:
                key = task.occurrence_key(date.today())
                task.fired = [k for k in task.fired if k != key]
                app._popup_open.pop((task.tid, key), None)
                app._remind(task, key)
        elif mode == "history":
            app.show_history()
        print("window ready, pid =", os.getpid(), "dark =", dark, "mode =", mode, flush=True)

    def report() -> None:
        # 打印实际状态，便于确认「截图是空的」是抓图问题还是界面问题
        print(f"[状态] 列表行数={len(app.tree.get_children())} 可见任务={len(app.visible_tasks())} "
              f"配色={app.palette['bg']} 窗口={root.state()}", flush=True)

    root.after(500, prepare)
    root.after(1500, report)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
