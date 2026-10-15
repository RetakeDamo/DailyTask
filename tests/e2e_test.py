# -*- coding: utf-8 -*-
"""端到端验证：真实入口启动 → 打卡 → 重新加载后记录仍在。

用法： python tests/e2e_test.py
"""
from __future__ import annotations

import subprocess
import sys
import time
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from daily_task.history import HistoryStore  # noqa: E402
from daily_task.settings import Settings  # noqa: E402
from daily_task.tasks import Task, TaskStore  # noqa: E402
from daily_task.ui import PALETTES, TaskApp  # noqa: E402

WORK = BASE / ".build" / "e2e-data"


def secret_done_trip(root: tk.Tk, store: TaskStore, history: HistoryStore, settings: Settings) -> None:
    """模拟用户：打卡 → 打开完成记录 → 切深色 → 退出。"""
    app = TaskApp(root, store, settings, silent_start=False, history=history)
    app._startup_report()
    root.update()

    for task in store.tasks:
        app.tree.selection_set(task.tid)
        app.toggle_done()
        root.update()
    assert len(history.records) == 2, f"应记录 2 条，实际 {len(history.records)}"

    app.show_history()
    root.update()
    window = app._history_window
    assert window is not None and window.alive()
    assert len(window.tree.get_children()) >= 1, "完成记录窗口应有内容"
    assert window.kind_var.get() == "all"

    app.toggle_dark_mode()
    root.update()
    assert app.palette["bg"] == PALETTES["dark"]["bg"]
    assert window.palette["bg"] == PALETTES["dark"]["bg"], "记录窗口应同步深色"

    app.quit_app()
    root.update()


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    for item in WORK.iterdir():
        if item.is_file():
            item.unlink()

    # ---------- 第一次运行：创建任务并打卡 ----------
    store = TaskStore(WORK)
    store.add(Task(title="每天喝水", kind="daily", time="09:00", notes="八杯水"))
    store.add(Task(title="提交周报", kind="once",
                   date=date.today().strftime("%Y-%m-%d"), time="18:00"))
    store.save()
    settings = Settings.load(WORK)
    settings.windows_toast = False
    settings.sound = False
    settings.dark_mode = False
    settings.save()

    root = tk.Tk()
    root.withdraw()
    secret_done_trip(root, store, HistoryStore(WORK), settings)
    print("[i] 第一次运行：打卡 2 次，已切到深色并退出")

    # ---------- 第二次运行：模拟重启 ----------
    store2 = TaskStore(WORK)
    store2.load()
    history2 = HistoryStore(WORK)
    history2.load()
    settings2 = Settings.load(WORK)

    assert len(store2.tasks) == 2, "任务应持久化"
    assert store2.tasks[0].last_done == date.today().strftime("%Y-%m-%d"), "每日任务打卡状态应持久化"
    assert store2.tasks[1].done is True, "一次性任务完成状态应持久化"
    assert len(history2.records) == 2, f"完成记录应持久化，实际 {len(history2.records)}"
    assert settings2.dark_mode is True, "深色模式应持久化"
    assert history2.summary()["today"] == 2, history2.summary()
    print("[i] 第二次运行：任务/记录/深色设置都已从磁盘恢复")

    root2 = tk.Tk()
    root2.withdraw()
    app2 = TaskApp(root2, store2, settings2, silent_start=False, history=history2)
    app2._startup_report()
    root2.update()
    assert len(app2.tree.get_children()) == 2
    assert app2.palette["bg"] == PALETTES["dark"]["bg"], "重启后应仍是深色"
    # 撤销打卡应删掉记录
    app2.tree.selection_set(store2.tasks[0].tid)
    app2.toggle_done()
    root2.update()
    assert len(history2.records) == 1, "撤销打卡应删除对应记录"
    assert history2.records[0].title == "提交周报", "剩下的应是未撤销的那条"
    app2.quit_app()

    # ---------- 真实入口：--version 与数据目录参数 ----------
    proc = subprocess.run([sys.executable, str(BASE / "main.py"), "--version"],
                          capture_output=True, timeout=60)
    assert proc.returncode == 0 and b"1.1.0" in proc.stdout, proc.stdout
    print("[i] 真实入口 --version:", proc.stdout.decode("utf-8", "ignore").strip())

    # ---------- CSV 导出 ----------
    csv_path = WORK / "e2e.csv"
    history2.export_csv(csv_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "提交周报" in text and "完成时间" in text, text[:200]
    assert "每天喝水" not in text, "被撤销的记录不应出现在导出里"
    print("[i] CSV 导出正常:", csv_path.name, len(text), "字节")

    print("[OK] 端到端验证通过：打卡 → 保存 → 重启恢复 → 撤销 → 深色持久化 → CSV 导出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
