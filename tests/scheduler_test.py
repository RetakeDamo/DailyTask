# -*- coding: utf-8 -*-
"""调度逻辑测试：验证「到点提醒」「不重复提醒」「稍后提醒」「打卡后不再提醒」。

用法： python tests/scheduler_test.py
"""
from __future__ import annotations

import sys
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from daily_task.settings import Settings  # noqa: E402
from daily_task.tasks import Task, TaskStore  # noqa: E402
from daily_task.ui import TaskApp  # noqa: E402

WORKDIR = BASE / ".build" / "sched-data"


def reset() -> TaskStore:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    for item in WORKDIR.iterdir():
        item.unlink()
    return TaskStore(WORKDIR)


def fresh_app(root: tk.Tk, store: TaskStore) -> TaskApp:
    settings = Settings.load(WORKDIR)
    settings.windows_toast = False
    settings.sound = False
    app = TaskApp(root, store, settings, silent_start=False)
    root.update()
    return app


def main() -> int:
    import time
    # 避免测试过程中跨越整分钟导致“到点时刻”变化
    if datetime.now().second > 50:
        time.sleep(62 - datetime.now().second)

    now = datetime.now()
    hhmm = now.strftime("%H:%M")
    past = (now - timedelta(minutes=3)).strftime("%H:%M")
    future = (now + timedelta(minutes=10)).strftime("%H:%M")

    store = reset()
    daily_due = store.add(Task(title="到点的每日任务", kind="daily", time=hhmm))
    daily_later = store.add(Task(title="晚一点的每日任务", kind="daily", time=future))
    once_due = store.add(Task(title="到点的一次性任务", kind="once",
                              date=date.today().strftime("%Y-%m-%d"), time=past))

    root = tk.Tk()
    root.withdraw()
    app = fresh_app(root, store)

    # 1) 到点的任务应有 fire_key
    assert daily_due.fire_key(date.today()), "到点的每日任务应触发"
    assert once_due.fire_key(date.today()), "到点的一次性任务应触发"
    assert daily_later.fire_key(date.today()) is None, "未到点不应触发"

    # 2) tick 后应标记为已提醒，且不会重复提醒
    app.tick(force=True)
    root.update()
    assert daily_due.fired, "tick 后应记录已提醒"
    assert daily_due.fire_key(date.today()) is None, "同一次提醒不应重复触发"
    assert once_due.fired, "一次性任务应记录已提醒"

    # 3) 每日任务打卡后，当天不再提醒
    app.mark_done(daily_due)
    root.update()
    assert daily_due.last_done == date.today().strftime("%Y-%m-%d")
    assert daily_due.fire_key(date.today()) is None, "已打卡的任务不应再提醒"
    assert daily_due.status() == "daily_done"
    assert daily_due.next_text() == "今日已完成"

    # 4) 停用的任务不提醒
    daily_later.enabled = False
    assert daily_later.fire_key(date.today()) is None, "停用任务不应提醒"
    assert daily_later.status() == "off"

    # 5) 稍后提醒：把已提醒的挪到 5 分钟后，期间不提醒，过后恢复
    task = store.add(Task(title="稍后提醒任务", kind="daily", time=hhmm))
    assert task.fire_key(date.today()), "新任务到点应可提醒"
    app.tick(force=True)
    root.update()
    assert task.fire_key(date.today()) is None, "刚提醒过不应立刻再提醒"
    task.snooze(task.occurrence_key(date.today()), 5)
    assert task.fire_key(date.today()) is None, "延后期间不应提醒"
    task.snooze_until = (datetime.now() - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M")
    assert task.fire_key(date.today()), "延后时间到后应重新提醒"

    # 6) 一次性任务提醒后自动完成
    store2 = reset()
    once2 = store2.add(Task(title="自动完成的会议", kind="once",
                            date=date.today().strftime("%Y-%m-%d"), time=past))
    app2_settings = Settings.load(WORKDIR)
    app2_settings.windows_toast = False
    app2_settings.sound = False
    app2_settings.one_time_auto_done = True
    app2_settings.save()
    app2 = TaskApp(root, store2, app2_settings, silent_start=False)
    root.update()
    app2.tick(force=True)
    root.update()
    assert once2.done, "开启自动完成后，一次性任务提醒后应标记完成"
    assert once2.status() == "done_once"

    # 7) 星期限定：只在指定星期提醒
    today_idx = date.today().weekday()
    other = (today_idx + 1) % 7
    store3 = reset()
    only_other = store3.add(Task(title="只在别的星期", kind="daily", time=hhmm, weekdays=[other]))
    app3_settings = Settings.load(WORKDIR)
    app3_settings.windows_toast = False
    app3_settings.sound = False
    app3_settings.one_time_auto_done = False
    app3_settings.save()
    app3 = TaskApp(root, store3, app3_settings, silent_start=False)
    root.update()
    app3.tick(force=True)
    root.update()
    assert only_other.fire_key(date.today()) is None, "非指定星期不应提醒"
    assert only_other.next_text() != "今日已完成"

    app.quit_app()
    print("[OK] 调度测试通过：到点提醒 / 不重复 / 打卡后停止 / 停用 / 稍后提醒 / 自动完成 / 星期限定")
    return 0


if __name__ == "__main__":
    sys.exit(main())
