# -*- coding: utf-8 -*-
"""完成记录与深色模式测试。

用法： python tests/history_test.py
"""
from __future__ import annotations

import sys
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from daily_task.history import HistoryStore, Record  # noqa: E402
from daily_task.settings import Settings  # noqa: E402
from daily_task.tasks import Task, TaskStore  # noqa: E402
from daily_task.ui import PALETTES, TaskApp  # noqa: E402

WORKDIR = BASE / ".build" / "history-data"


def reset() -> Path:
    WORKDIR.mkdir(parents=True, exist_ok=True)
    for item in WORKDIR.iterdir():
        if item.is_file():
            item.unlink()
    return WORKDIR


def build() -> tuple:
    workdir = reset()
    store = TaskStore(workdir)
    daily = store.add(Task(title="每天喝水", kind="daily", time="09:00", notes="八杯水"))
    once = store.add(Task(title="提交报销单", kind="once",
                          date=date.today().strftime("%Y-%m-%d"), time="10:00"))
    store.save()

    settings = Settings.load(workdir)
    settings.windows_toast = False
    settings.sound = False
    settings.dark_mode = False
    settings.save()

    history = HistoryStore(workdir)
    history.load()

    root = tk.Tk()
    root.withdraw()
    app = TaskApp(root, store, settings, silent_start=False, history=history)
    root.update()
    app.refresh()          # 无头环境下主动刷新一次，确保列表已填充
    root.update()
    return root, app, store, settings, history, daily, once


def main() -> int:
    root, app, store, settings, history, daily, once = build()

    # 1) 打卡会写入一条记录
    app.tree.selection_set(daily.tid)
    app.toggle_done()
    root.update()
    assert len(history.records) == 1, "打卡后应有一条完成记录"
    record = history.records[0]
    assert record.title == "每天喝水"
    assert record.kind == "daily"
    assert record.source == "list"
    assert record.notes == "八杯水"
    assert record.day == date.today().strftime("%Y-%m-%d"), "记录日期应为今天"
    assert record.when is not None, "记录时间应可解析"

    # 2) 取消打卡会删掉记录
    app.toggle_done()
    root.update()
    assert len(history.records) == 0, "取消打卡应删除该次记录"

    # 3) 提醒卡片上点「标记完成」记来源为 card
    app.tree.selection_set(daily.tid)
    app.mark_done(daily, source="card")
    root.update()
    assert history.records[-1].source == "card", "卡片完成的来源应为 card"
    assert history.records[-1].source_text == "提醒卡片"

    # 4) 一次性任务打卡同样记录
    app.tree.selection_set(once.tid)
    app.toggle_done()
    root.update()
    assert once.done and len(history.records) == 2
    assert history.records[-1].kind_text == "一次性"

    # 5) 统计：今天 / 累计 / 连续天数
    summary = history.summary()
    assert summary["today"] == 2 and summary["total"] == 2, summary
    assert summary["streak"] == 1 and summary["best_streak"] == 1, summary
    assert history.count_on(date.today()) == 2

    # 6) 昨天也有一条时，连续天数为 2
    yesterday = datetime.now() - timedelta(days=1)
    history.add(title="昨天跑步", kind="daily", schedule="20:00 · 每天", stamp=yesterday)
    assert history.current_streak() == 2, history.current_streak()
    assert history.current_streak() == history.best_streak()
    counts = history.daily_counts(7)
    assert len(counts) == 7 and counts[-1][1] == 2 and counts[-2][1] == 1, counts

    # 7) 查询筛选
    assert len(history.query(days=1)) == 2, "只查今天应有 2 条"
    assert len(history.query(days=7, kind="once")) == 1, "按类型筛选"
    assert len(history.query(days=7, keyword="跑步")) == 1, "按关键词筛选"
    assert history.query(days=0)[0].stamp >= history.query(days=0)[-1].stamp, "应按时间倒序"

    # 8) 提前 / 延后计算
    early = Record(title="早到", kind="daily", schedule="09:00 · 每天",
                   stamp=date.today().strftime("%Y-%m-%d") + " 08:30:00")
    late = Record(title="迟到", kind="daily", schedule="09:00 · 每天",
                  stamp=date.today().strftime("%Y-%m-%d") + " 10:15:00")
    ontime = Record(title="准点", kind="daily", schedule="09:00 · 每天",
                    stamp=date.today().strftime("%Y-%m-%d") + " 09:00:30")
    assert early.is_late() is False and "早 30 分钟" in early.delay_text()
    assert late.is_late() is True and "晚 1 小时15 分" in late.delay_text()
    assert ontime.is_late() is False and ontime.delay_text() == "准点"

    # 9) 导出 CSV
    csv_path = WORKDIR / "out.csv"
    count = history.export_csv(csv_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    assert count == len(history.records) and "完成时间" in text and "每天喝水" in text, text[:200]

    # 10) 保存 -> 重新读取
    history.save()
    again = HistoryStore(WORKDIR)
    again.load()
    assert len(again.records) == len(history.records), "记录应能持久化"
    assert again.records[0].title == history.records[0].title

    # 11) 完成记录窗口：构建 / 筛选 / 主题切换 / 关闭
    app.tree.selection_set(daily.tid)
    app.show_history()
    root.update()
    window = app._history_window
    assert window is not None and window.alive(), "记录窗口应能打开"
    base_rows = len(window.tree.get_children())
    assert base_rows >= 2, f"近 7 天应至少 2 条，实际 {base_rows}"
    window.keyword_var.set("报销")
    root.update()
    assert len(window.tree.get_children()) == 1, "记录窗口搜索应生效"
    window.keyword_var.set("")
    window.kind_var.set("once")
    window.refresh()
    root.update()
    assert len(window.tree.get_children()) == 1, "记录窗口类型筛选应生效"
    window.kind_var.set("all")
    window.range_var.set("今天")
    window.refresh()
    root.update()
    assert len(window.tree.get_children()) == 2, "时间范围筛选应生效"
    window.range_var.set("近 7 天")
    window.refresh()
    row = window.tree.get_children()[0]
    assert window.tree.item(row, "values")[0], "记录行应有完成时间"

    # 12) 深色模式：切换后控件颜色跟着变
    assert settings.dark_mode is False
    assert app.palette["bg"] == PALETTES["light"]["bg"]
    before_bg = app.clock_label.cget("bg")
    app.toggle_dark_mode()
    root.update()
    assert settings.dark_mode is True, "深色模式应写入设置"
    assert app.palette["bg"] == PALETTES["dark"]["bg"], "配色应切换到深色"
    assert app.clock_label.cget("bg") == PALETTES["dark"]["panel"], "时钟背景应跟着变"
    assert app.clock_label.cget("bg") != before_bg
    assert app.status_label.cget("bg") == PALETTES["dark"]["panel"]
    assert app.empty_label.cget("bg") == PALETTES["dark"]["bg"]
    assert app._theme_button.cget("text").startswith("☀"), "按钮文字应提示切回浅色"
    # 记录窗口也要跟着变色
    assert window.palette["bg"] == PALETTES["dark"]["bg"], "记录窗口应同步深色"
    assert window.summary_label.cget("bg") == PALETTES["dark"]["panel"]

    # 13) 结构未被重建（控件引用依然有效）
    app.refresh()
    app._tick()
    root.update()
    assert app.tree.get_children(), "切换主题后列表仍应可用"

    # 14) 切回浅色并持久化
    app.toggle_dark_mode(False)
    root.update()
    assert app.palette["bg"] == PALETTES["light"]["bg"]
    reloaded = Settings.load(WORKDIR)
    assert reloaded.dark_mode is False, "深色模式设置应能被保存/读取"
    app.toggle_dark_mode(True)
    root.update()
    assert Settings.load(WORKDIR).dark_mode is True, "深色模式应持久化为 True"

    app.quit_app()
    print("[OK] 完成记录与深色模式测试通过：打卡记录 / 撤销 / 来源 / 统计 / 连续天数 / 筛选 / 提前延后 / CSV / 持久化 / 主题切换")
    return 0


if __name__ == "__main__":
    sys.exit(main())
