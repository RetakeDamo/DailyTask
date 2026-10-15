# -*- coding: utf-8 -*-
"""无头冒烟测试：构造主窗口、刷新列表、触发调度，验证不抛异常。

用法： python tests/smoke_test.py
"""
from __future__ import annotations

import sys
import tempfile
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_task.notify import _xml_escape, show_windows_toast  # noqa: E402
from daily_task.settings import Settings, launch_command, set_autostart  # noqa: E402
from daily_task.tasks import Task, TaskStore  # noqa: E402
from daily_task.ui import TaskApp, TaskDialog  # noqa: E402


def build_store(data_dir: Path) -> TaskStore:
    store = TaskStore(data_dir)
    now = datetime.now()
    soon = (now + timedelta(minutes=2)).strftime("%H:%M")
    past = (now - timedelta(minutes=1)).strftime("%H:%M")

    store.add(Task(title="每日喝水", kind="daily", time=soon, notes="多喝热水"))
    store.add(Task(title="正在到点的任务", kind="daily", time=past, notes="应该被调度"))
    store.add(Task(title="工作日站会", kind="daily", time="09:35", weekdays=[0, 1, 2, 3, 4]))
    store.add(Task(title="每周五周报", kind="daily", time="18:05", weekdays=[4]))
    store.add(Task(title="明天体检", kind="once",
                   date=(date.today() + timedelta(days=1)).strftime("%Y-%m-%d"), time="08:30"))
    store.add(Task(title="三天后的会议", kind="once",
                   date=(date.today() + timedelta(days=3)).strftime("%Y-%m-%d"), time="14:00"))
    store.add(Task(title="过期的旧任务", kind="once",
                   date=(date.today() - timedelta(days=2)).strftime("%Y-%m-%d"), time="07:00"))
    store.add(Task(title="停用的任务", kind="daily", time="10:00", enabled=False))
    store.add(Task(title="已经打过卡的", kind="daily", time="08:00",
                   last_done=date.today().strftime("%Y-%m-%d")))
    return store


def main() -> int:
    workdir = Path(__file__).resolve().parent.parent / ".build" / "smoke-data"
    if workdir.exists():
        for item in workdir.iterdir():
            item.unlink()
    workdir.mkdir(parents=True, exist_ok=True)
    store = build_store(workdir)
    store.save()

    # 落盘再读回来，验证序列化往返
    reloaded = TaskStore(workdir)
    reloaded.load()
    assert len(reloaded.tasks) == len(store.tasks), "序列化往返任务数量不一致"

    # 序列化后调度逻辑不应抛异常
    fired = [t.fire_key(date.today()) for t in reloaded.tasks]
    assert any(fired), "应当至少有一个任务到点需要提醒"

    settings = Settings.load(workdir)
    settings.windows_toast = False   # 测试时不真的发系统通知
    settings.sound = False
    settings.save()

    root = tk.Tk()
    root.withdraw()
    app = TaskApp(root, reloaded, settings, silent_start=True)
    root.update()
    app.refresh()
    root.update()
    app.tick(force=True)
    root.update()

    rows = app.tree.get_children()
    assert len(rows) == len(reloaded.tasks), f"列表行数 {len(rows)} != 任务数 {len(reloaded.tasks)}"

    # 逐个任务验证状态文案
    for task in reloaded.tasks:
        _ = task.status(), task.next_text()

    # 打卡 / 取消打卡
    app.tree.selection_set(reloaded.tasks[0].tid)
    app.toggle_done()
    assert reloaded.tasks[0].last_done == date.today().strftime("%Y-%m-%d"), "每日任务打卡失败"
    app.toggle_done()
    assert reloaded.tasks[0].last_done == "", "取消打卡失败"

    # 一次性任务打卡
    once = reloaded.tasks[4]
    app.tree.selection_set(once.tid)
    app.toggle_done()
    assert once.done, "一次性任务打卡失败"

    # 停用 / 启用
    app.tree.selection_set(reloaded.tasks[1].tid)
    app.toggle_enabled()
    assert not reloaded.tasks[1].enabled, "停用失败"
    app.toggle_enabled()
    assert reloaded.tasks[1].enabled, "启用失败"

    # 搜索过滤
    app.search_var.set("体检")
    app.refresh()
    assert len(app.tree.get_children()) == 1, "搜索过滤结果不正确"
    app.search_var.set("")
    app.refresh()

    # 稍后提醒
    app.tree.selection_set(reloaded.tasks[1].tid)
    app.snooze_selected(5)
    assert reloaded.tasks[1].snooze_until, "稍后提醒未生效"
    assert reloaded.tasks[1].fire_key(date.today()) is None, "延后期间不应再次提醒"

    # 编辑对话框（不保存，仅验证能正常构建与回收）
    dialog = TaskDialog(root, reloaded.tasks[0])
    root.update()
    dialog.kind_var.set("once")
    dialog._on_kind()
    dialog.kind_var.set("daily")
    dialog._on_kind()
    dialog._cancel()
    root.update()

    # 菜单勾选变量（验证不会被垃圾回收）
    var = app._bool_var(True)
    assert var.get() is True
    assert len(app._menu_vars) == 1
    # 设置开关
    before = app.settings.sound
    app.toggle_sound()
    assert app.settings.sound is not before
    app.toggle_sound()
    before = app.settings.show_finished
    app.toggle_show_finished()
    assert app.settings.show_finished is not before
    app.toggle_show_finished()
    app._set_auto_done(True)
    assert app.settings.one_time_auto_done is True
    app._set_auto_done(False)
    # 文本工具
    from daily_task.tasks import human_delta, valid_date, valid_time
    now = datetime.now()
    assert valid_time("09:30") and not valid_time("25:00")
    assert valid_date("2026-01-02") and not valid_date("2026-13-40")
    assert human_delta(now + timedelta(minutes=5), now) == "5 分钟后"
    assert "已过" in human_delta(now - timedelta(hours=2), now)
    assert human_delta(now + timedelta(days=1), now).startswith("明天")

    # 自启注册表读写（写一个临时值再删掉，避免影响用户设置）
    ok, info = set_autostart(True)
    if ok:
        assert Settings.load(workdir).autostart in (True, False)
        set_autostart(False)
    print("[i] 开机自启注册表可用:", ok, info if not ok else "")

    print("[i] 自启命令:", launch_command())
    print("[i] XML 转义:", _xml_escape("a<b>&\"'"))

    # 单实例判定：本进程拿到标记后，后续再判断必须为「已有实例在运行」
    import main as entry
    entry.release_single_instance(workdir)
    results = [entry.acquire_single_instance(workdir) for _ in range(4)]
    assert results[0] is True, f"首次应取得单实例资格，实际 {results}"
    assert all(r is False for r in results[1:]), f"后续应判定为已在运行，实际 {results}"
    entry.release_single_instance(workdir)
    assert not (Path(workdir) / entry.LOCK_FILE_NAME).exists(), "释放后不应留下 pid 文件"
    print(f"[i] 单实例判定: OK（{results[0]} → {results[1:]}）")

    stats = reloaded.stats()
    print("[i] 统计:", stats)
    assert stats["total"] == len(reloaded.tasks)

    app.quit_app()
    print("[OK] 冒烟测试通过，数据目录:", workdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
