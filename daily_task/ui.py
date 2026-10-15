# -*- coding: utf-8 -*-
"""主界面：任务列表、增删改查、提醒调度。"""
from __future__ import annotations

import json
import sys
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

from .history import HistoryStore, Record
from .notify import ToastPopup, play_sound, show_windows_toast
from .settings import Settings, consume_show_signal, set_autostart, verify_launch_target
from .tasks import (
    ALL_WEEKDAYS,
    DATE_FMT,
    TIME_FMT,
    WEEKDAY_NAMES,
    Task,
    TaskStore,
    valid_date,
    valid_time,
    weekdays_text,
)

APP_TITLE = "每日任务提醒"

# 配色：每个主题一套，界面里统一通过 self.palette 取色
PALETTES = {
    "light": {
        "bg": "#f5f7fb", "panel": "#ffffff", "panel_alt": "#fafbfd", "line": "#e4e8f0",
        "text": "#101828", "text_soft": "#475569", "muted": "#98a2b3",
        "accent": "#2f6feb", "accent_soft": "#dbe8ff", "accent_text": "#0b1a33",
        "now": "#c2410c", "expired": "#b42318", "done": "#0f7b3f", "waiting": "#475569",
        "sel_bg": "#dbe8ff", "sel_fg": "#0b1a33", "shadow": "#d8dde5",
    },
    "dark": {
        "bg": "#12161f", "panel": "#1a1f2b", "panel_alt": "#1f2533", "line": "#2a3242",
        "text": "#e8edf7", "text_soft": "#aab6ca", "muted": "#7b879c",
        "accent": "#4c8dff", "accent_soft": "#33436b", "accent_text": "#eaf1ff",
        "now": "#ffa657", "expired": "#ff7b72", "done": "#56d364", "waiting": "#8b97ab",
        "sel_bg": "#2b3a5c", "sel_fg": "#ffffff", "shadow": "#0d1016",
    },
}


def resource_path(name: str) -> Path:
    """兼容源码运行与 PyInstaller 打包后的资源路径。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / name
    return Path(__file__).resolve().parent.parent / name

STATUS_META = {
    "now":      ("⏰ 待办", "now"),
    "soon":     ("🕒 即将", "accent"),
    "waiting":  ("⏳ 等待", "waiting"),
    "expired":  ("⚠ 已错过", "expired"),
    "daily_done": ("✅ 今日完成", "done"),
    "done_once": ("✅ 已完成", "done"),
    "off":      ("⏸ 已停用", "muted"),
}

KIND_META = {"daily": "每日循环", "once": "一次性"}


def make_badge(parent: tk.Misc, text: str, palette: Dict[str, str], fg: str, bg: str,
               bold: bool = True) -> tk.Label:
    """小标签，用于「完成记录」里的统计数据；配色会随主题更新。"""
    widget = tk.Label(parent, text=text, fg=palette.get(fg, palette["text"]),
                      bg=palette.get(bg, palette["panel_alt"]), padx=10, pady=5,
                      font=("Microsoft YaHei UI", 9, "bold" if bold else "normal"))
    style_widget(widget, palette, role=bg, fg=fg)
    return widget


def center_on_screen(win: tk.Misc, parent: Optional[tk.Misc] = None) -> None:
    win.update_idletasks()
    w, h = win.winfo_width(), win.winfo_height()
    if parent is not None:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x, y = px + (pw - w) // 2, py + (ph - h) // 3
    else:
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 3
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


# --------------------------------------------------------------------------- #
# 新建 / 编辑对话框
# --------------------------------------------------------------------------- #
class TaskDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, task: Optional[Task] = None, palette: Optional[Dict[str, str]] = None):
        super().__init__(master)
        self.result: Optional[Task] = None
        self.editing = task is not None
        self.task = task or Task()
        self.palette = palette or PALETTES["light"]
        p = self.palette

        self.title("编辑任务" if self.editing else "新建任务")
        self.configure(bg=p["panel"])
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        body = tk.Frame(self, bg=p["panel"], padx=22, pady=18)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=("编辑任务" if self.editing else "新建任务"),
                 bg=p["panel"], fg=p["text"], font=("Microsoft YaHei UI", 14, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w")
        tk.Label(body, text="每日循环任务到点提醒；一次性任务只在指定日期提醒一次。",
                 bg=p["panel"], fg=p["muted"], font=("Microsoft YaHei UI", 9)).grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(2, 14))

        # 任务名称
        tk.Label(body, text="任务名称", bg=p["panel"], fg=p["text_soft"],
                 font=("Microsoft YaHei UI", 10)).grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.title_var = tk.StringVar(value=self.task.title)
        self.title_entry = ttk.Entry(body, textvariable=self.title_var, width=42, font=("Microsoft YaHei UI", 10))
        self.title_entry.grid(row=3, column=0, columnspan=4, sticky="we", ipady=3)

        # 类型
        tk.Label(body, text="任务类型", bg=p["panel"], fg=p["text_soft"],
                 font=("Microsoft YaHei UI", 10)).grid(row=4, column=0, sticky="w", pady=(14, 4))
        self.kind_var = tk.StringVar(value=self.task.kind)
        kind_row = tk.Frame(body, bg=p["panel"])
        kind_row.grid(row=5, column=0, columnspan=4, sticky="w")
        ttk.Radiobutton(kind_row, text="每日循环", value="daily", variable=self.kind_var,
                        command=self._on_kind).pack(side="left")
        ttk.Radiobutton(kind_row, text="一次性", value="once", variable=self.kind_var,
                        command=self._on_kind).pack(side="left", padx=(18, 0))

        # 时间
        tk.Label(body, text="提醒时间", bg=p["panel"], fg=p["text_soft"],
                 font=("Microsoft YaHei UI", 10)).grid(row=6, column=0, sticky="w", pady=(14, 4))
        time_row = tk.Frame(body, bg=p["panel"])
        time_row.grid(row=7, column=0, columnspan=4, sticky="w")
        self.hour_var = tk.StringVar()
        self.minute_var = tk.StringVar()
        self.hour_box = ttk.Combobox(time_row, textvariable=self.hour_var, width=4, state="readonly",
                                     values=[f"{h:02d}" for h in range(24)], font=("Consolas", 10))
        self.hour_box.pack(side="left")
        tk.Label(time_row, text=":", bg=p["panel"], fg=p["text"], font=("Consolas", 11, "bold")).pack(side="left", padx=2)
        self.minute_box = ttk.Combobox(time_row, textvariable=self.minute_var, width=4, state="readonly",
                                       values=[f"{m:02d}" for m in range(0, 60, 5)], font=("Consolas", 10))
        self.minute_box.pack(side="left")
        self.now_button = ttk.Button(time_row, text="当前时间", width=10, command=self._use_now)
        self.now_button.pack(side="left", padx=(12, 0))

        # 一次性：日期
        self.date_label = tk.Label(body, text="执行日期", bg=p["panel"], fg=p["text_soft"],
                                   font=("Microsoft YaHei UI", 10))
        self.date_label.grid(row=8, column=0, sticky="w", pady=(14, 4))
        self.date_row = tk.Frame(body, bg=p["panel"])
        self.date_row.grid(row=9, column=0, columnspan=4, sticky="w")
        self.date_var = tk.StringVar(value=self.task.date or date.today().strftime(DATE_FMT))
        self.date_entry = ttk.Entry(self.date_row, textvariable=self.date_var, width=14, font=("Consolas", 10))
        self.date_entry.pack(side="left", ipady=2)
        tk.Label(self.date_row, text="格式 2025-12-31", bg=p["panel"], fg=p["muted"],
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(8, 0))
        for label, offset in (("今天", 0), ("明天", 1), ("下周", 7)):
            ttk.Button(self.date_row, text=label, width=6,
                       command=lambda o=offset: self.date_var.set(
                           (date.today() + timedelta(days=o)).strftime(DATE_FMT))).pack(side="left", padx=(6, 0))

        # 每日：星期
        self.week_label = tk.Label(body, text="重复日（不选＝每天）", bg=p["panel"], fg=p["text_soft"],
                                   font=("Microsoft YaHei UI", 10))
        self.week_label.grid(row=10, column=0, sticky="w", pady=(14, 4))
        self.week_row = tk.Frame(body, bg=p["panel"])
        self.week_row.grid(row=11, column=0, columnspan=4, sticky="w")
        self.week_vars: List[tk.BooleanVar] = []
        for idx in range(7):
            var = tk.BooleanVar(value=bool(self.task.weekdays and idx in self.task.weekdays))
            self.week_vars.append(var)
            ttk.Checkbutton(self.week_row, text="周" + WEEKDAY_NAMES[idx], variable=var).pack(side="left")
        ttk.Button(self.week_row, text="工作日", width=7,
                   command=lambda: self._set_weekdays([0, 1, 2, 3, 4])).pack(side="left", padx=(10, 0))
        ttk.Button(self.week_row, text="每天", width=6,
                   command=lambda: self._set_weekdays(ALL_WEEKDAYS)).pack(side="left", padx=(4, 0))

        # 备注
        tk.Label(body, text="备注（可留空）", bg=p["panel"], fg=p["text_soft"],
                 font=("Microsoft YaHei UI", 10)).grid(row=12, column=0, sticky="w", pady=(14, 4))
        self.notes_text = tk.Text(body, height=3, width=42, font=("Microsoft YaHei UI", 9),
                                  relief="solid", bd=1, highlightthickness=0,
                                  bg=p["panel_alt"], fg=p["text"], insertbackground=p["text"])
        self.notes_text.grid(row=13, column=0, columnspan=4, sticky="we")
        self.notes_text.insert("1.0", self.task.notes)

        # 按钮
        buttons = tk.Frame(body, bg=p["panel"])
        buttons.grid(row=14, column=0, columnspan=4, sticky="e", pady=(18, 0))
        ttk.Button(buttons, text="保存", width=12, command=self._save).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="取消", width=10, command=self._cancel).pack(side="right")

        self._load_time()
        self._on_kind()
        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self._cancel())
        center_on_screen(self, master.winfo_toplevel())
        self.title_entry.focus_set()
        self.grab_set()

    # ---------------- 辅助 ---------------- #
    def _load_time(self) -> None:
        try:
            parsed = datetime.strptime(self.task.time, TIME_FMT)
            hour, minute = parsed.hour, parsed.minute
        except Exception:
            hour, minute = 9, 0
        self.hour_var.set(f"{hour:02d}")
        self.minute_var.set(f"{(minute // 5) * 5:02d}")

    def _use_now(self) -> None:
        now = datetime.now() + timedelta(minutes=1)
        self.hour_var.set(f"{now.hour:02d}")
        self.minute_var.set(f"{(now.minute // 5) * 5:02d}")

    def _set_weekdays(self, days: List[int]) -> None:
        for idx, var in enumerate(self.week_vars):
            var.set(idx in days)

    def _on_kind(self) -> None:
        daily = self.kind_var.get() == "daily"
        state_daily = "normal" if daily else "disabled"
        state_once = "disabled" if daily else "normal"
        for widget in (self.week_label, *self.week_row.winfo_children()):
            self._set_state(widget, state_daily)
        for widget in (self.date_label, self.date_entry):
            self._set_state(widget, state_once)
        for widget in self.date_row.winfo_children()[1:]:
            self._set_state(widget, state_once)

    def _set_state(self, widget: tk.Misc, state: str) -> None:
        try:
            if isinstance(widget, ttk.Widget):
                widget.configure(state=state)
            else:
                widget.configure(fg=self.palette["muted"] if state == "disabled" else self.palette["text_soft"])
        except Exception:
            pass

    def _collect(self) -> Optional[Task]:
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("缺少名称", "请填写任务名称。", parent=self)
            return None
        time_text = f"{self.hour_var.get()}:{self.minute_var.get()}"
        if not valid_time(time_text):
            messagebox.showwarning("时间有误", "提醒时间格式应为 HH:MM。", parent=self)
            return None
        kind = self.kind_var.get()
        date_text = ""
        weekdays = None
        if kind == "once":
            date_text = self.date_var.get().strip()
            if not valid_date(date_text):
                messagebox.showwarning("日期有误", "执行日期格式应为 2025-12-31。", parent=self)
                return None
        else:
            picked = [i for i, var in enumerate(self.week_vars) if var.get()]
            weekdays = None if (not picked or len(picked) == 7) else picked
        task = self.task
        task.title = title
        task.notes = self.notes_text.get("1.0", "end").strip()
        task.kind = kind
        task.time = time_text
        task.date = date_text
        task.weekdays = weekdays
        if kind == "once" and task.done and task.date != date_text:
            task.done = False          # 改了日期，重新生效
        return task

    def _save(self) -> None:
        task = self._collect()
        if task is None:
            return
        self.result = task
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


# --------------------------------------------------------------------------- #
# 关于 / 快捷键
# --------------------------------------------------------------------------- #
ABOUT_TEXT = """每日任务提醒  v1.1

· 每日循环任务：每天到点提醒，可指定只在某些星期提醒
· 一次性任务：只在指定日期和时间提醒一次

完成记录
  每次「今日打卡」或点提醒卡片上的「标记完成」，都会留下带时间的记录。
  点工具条「完成记录」可查看历史、按天/类型/关键词筛选、导出 CSV。
  底部状态栏会显示累计打卡次数与连续打卡天数。

深色模式
  点右上角「🌙 深色 / ☀ 浅色」按钮，或在「系统 ▾」菜单里勾选。
  设置会记住，下次启动仍是同样的配色。

提醒时会弹出右下角卡片，可「稍后 5 分钟 / 标记完成 / 知道了」，
同时会收到一条 Windows 系统通知，错过也能在通知中心回看。

快捷键
  Ctrl+N        新建任务
  Enter         编辑选中任务
  Space         今日打卡 / 取消打卡
  Delete        删除任务
  Ctrl+D        启用 / 停用
  Ctrl+H        完成记录
  Ctrl+L        切换深色模式
  Ctrl+R        立即检查提醒
  F5            刷新列表
  Esc           最小化到后台

小提示
  · 点右上角 × 只是最小化到后台，提醒照常工作
  · 需要真正退出：菜单「系统 → 退出」
  · 任务数据：%APPDATA%\\DailyTaskReminder\\tasks.json
  · 打卡记录：%APPDATA%\\DailyTaskReminder\\history.json
"""


# --------------------------------------------------------------------------- #
# 完成记录窗口
# --------------------------------------------------------------------------- #
HISTORY_COLUMNS = (
    ("stamp", "完成时间", 150, "w"),
    ("title", "任务名称", 210, "w"),
    ("kind", "类型", 90, "center"),
    ("schedule", "计划安排", 150, "w"),
    ("delay", "提前/延后", 100, "center"),
    ("source", "来源", 90, "center"),
    ("notes", "备注", 160, "w"),
)


class HistoryWindow(tk.Toplevel):
    """完成记录（打勾历史）：按天查看、搜索、导出 CSV。"""

    RANGE_OPTIONS = [("今天", 1), ("近 7 天", 7), ("近 30 天", 30), ("近 90 天", 90), ("全部", 0)]

    def __init__(self, master: tk.Misc, history: HistoryStore, palette: Dict[str, str]):
        super().__init__(master)
        self.history = history
        self.palette = palette
        self._records: List[Record] = []
        self._title_filter = ""

        self.title("完成记录")
        self.geometry("1000x620")
        self.minsize(760, 460)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.range_var = tk.StringVar(value="近 7 天")
        self.kind_var = tk.StringVar(value="all")
        self.keyword_var = tk.StringVar()
        self.keyword_var.trace_add("write", lambda *_: self.refresh())

        self._build()
        self.apply_theme(palette)
        self.refresh()
        center_on_screen(self, master.winfo_toplevel())

    # ------------------------------------------------------------------ #
    def alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def _build(self) -> None:
        p = self.palette

        def frame(parent: tk.Misc, role: str = "panel", **kw) -> tk.Frame:
            widget = tk.Frame(parent, bg=p[role], **kw)
            style_widget(widget, p, role=role)
            return widget

        def label(parent: tk.Misc, role: str = "panel", fg: str = "text", **kw) -> tk.Label:
            widget = tk.Label(parent, bg=p[role], fg=p[fg], **kw)
            style_widget(widget, p, role=role, fg=fg)
            return widget

        head = frame(self, "panel", height=64)
        head.pack(fill="x")
        head.pack_propagate(False)
        label(head, "panel", "text", text="完成记录",
              font=("Microsoft YaHei UI", 14, "bold")).pack(side="left", padx=(18, 0), pady=(14, 0))
        self.hint = label(head, "panel", "muted", text="", font=("Microsoft YaHei UI", 9))
        self.hint.pack(side="left", padx=(12, 0), pady=(18, 0))

        self.badges = frame(head, "panel")
        self.badges.pack(side="right", padx=(0, 18), pady=(16, 0))

        frame(self, "line", height=1).pack(fill="x")

        bar = frame(self, "panel")
        bar.pack(fill="x", padx=12, pady=(10, 6))
        label(bar, "panel", "muted", text="时间范围", font=("Microsoft YaHei UI", 9)).pack(side="left")
        self.range_box = ttk.Combobox(bar, textvariable=self.range_var, width=8, state="readonly",
                                      values=[name for name, _ in self.RANGE_OPTIONS],
                                      font=("Microsoft YaHei UI", 9))
        self.range_box.pack(side="left", padx=(6, 12))
        self.range_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        label(bar, "panel", "muted", text="类型", font=("Microsoft YaHei UI", 9)).pack(side="left")
        for text, value in (("全部", "all"), ("每日循环", "daily"), ("一次性", "once")):
            ttk.Radiobutton(bar, text=text, value=value, variable=self.kind_var,
                            command=self.refresh).pack(side="left", padx=(6, 0))

        self.search_entry = ttk.Entry(bar, textvariable=self.keyword_var, width=16)
        self.search_entry.pack(side="right", ipady=2)
        label(bar, "panel", "muted", text="搜索", font=("Microsoft YaHei UI", 9)).pack(side="right", padx=(8, 4))

        wrap = frame(self, "bg")
        wrap.pack(fill="both", expand=True, padx=12)

        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in HISTORY_COLUMNS],
                                 show="headings", selectmode="browse")
        for key, text, width, anchor in HISTORY_COLUMNS:
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key in ("title", "notes")))
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.empty_label = label(wrap, "bg", "muted",
                                 text="还没有打卡记录\n\n在任务列表里点「今日打卡」，或点提醒卡片上的「标记完成」，"
                                      "这里就会留下记录。",
                                 justify="center", font=("Microsoft YaHei UI", 11))

        footer = frame(self, "panel")
        footer.pack(fill="x", pady=(8, 0))
        frame(footer, "line", height=1).pack(fill="x")
        inner = frame(footer, "panel")
        inner.pack(fill="x", padx=14, pady=7)
        self.summary_label = label(inner, "panel", "text_soft", text="", font=("Microsoft YaHei UI", 9))
        self.summary_label.pack(side="left")
        ttk.Button(inner, text="关闭", width=8, command=self.destroy).pack(side="right")
        ttk.Button(inner, text="导出 CSV…", width=12, command=self.export_csv).pack(side="right", padx=(0, 8))
        ttk.Button(inner, text="清空记录", width=10, command=self.clear_all).pack(side="right", padx=(0, 8))
        ttk.Button(inner, text="刷新", width=8, command=self.refresh).pack(side="right", padx=(0, 8))
        self._configure_tags()

    # ------------------------------------------------------------------ #
    def apply_theme(self, palette: Dict[str, str]) -> None:
        """主题切换：原地重绘记录窗口的控件颜色。"""
        self.palette = palette
        restyle_tree(self, palette)
        self._configure_tags()

    def _configure_tags(self) -> None:
        p = self.palette
        self.tree.tag_configure("odd", background=p["panel_alt"])
        self.tree.tag_configure("plain", background=p["panel"])
        self.tree.tag_configure("late", foreground=p["expired"])
        self.tree.tag_configure("early", foreground=p["done"])

    def _range_days(self) -> int:
        for name, days in self.RANGE_OPTIONS:
            if name == self.range_var.get():
                return days
        return 7

    def focus_task(self, title: str) -> None:
        self._title_filter = title
        if hasattr(self, "hint"):
            self.hint.configure(text=f"已筛选任务：{title}（清空搜索框可取消）")
        self.keyword_var.set(title)

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        if not self.alive():
            return
        p = self.palette
        self._records = self.history.query(
            days=self._range_days(),
            keyword=self.keyword_var.get(),
            kind=self.kind_var.get(),
        )
        self.tree.delete(*self.tree.get_children())
        for index, record in enumerate(self._records):
            late = record.is_late()
            tags = ["odd" if index % 2 else "plain"]
            if late is True:
                tags.append("late")
            elif late is False:
                tags.append("early")
            self.tree.insert("", "end", values=(
                record.stamp, record.title, record.kind_text, record.schedule,
                record.delay_text(), record.source_text, record.notes,
            ), tags=tuple(tags))

        if self._records:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.42, anchor="center")
            if self.history.records:
                self.empty_label.configure(text="该范围内没有记录\n换个时间范围或清空搜索试试。")

        self._render_badges()
        summary = self.history.summary()
        shown = len(self._records)
        self.summary_label.configure(
            text=f"当前显示 {shown} 条　·　累计 {summary['total']} 次　·　今天 {summary['today']} 次　·　"
                 f"连续 {summary['streak']} 天（最长 {summary['best_streak']} 天）"
        )

    def _render_badges(self) -> None:
        p = self.palette
        for child in self.badges.winfo_children():
            child.destroy()
        summary = self.history.summary()
        make_badge(self.badges, f"累计 {summary['total']}", p, "accent_text", "accent_soft").pack(side="left", padx=(0, 6))
        make_badge(self.badges, f"今天 {summary['today']}", p, "done", "panel_alt").pack(side="left", padx=(0, 6))
        make_badge(self.badges, f"连续 {summary['streak']} 天", p, "now", "panel_alt").pack(side="left")

    # ------------------------------------------------------------------ #
    def export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="导出完成记录", defaultextension=".csv",
            initialfile=f"打卡记录-{date.today().strftime('%Y%m%d')}.csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            count = self.history.export_csv(Path(path), self._records or None)
            messagebox.showinfo("导出完成", f"已导出 {count} 条记录到：\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)

    def clear_all(self) -> None:
        if not self.history.records:
            messagebox.showinfo("没有记录", "当前没有任何打卡记录。", parent=self)
            return
        if not messagebox.askyesno("清空记录", "确定清空全部打卡记录吗？此操作不可撤销。", parent=self):
            return
        removed = self.history.clear()
        self.history.save()
        self.refresh()
        messagebox.showinfo("已清空", f"已删除 {removed} 条记录。", parent=self)


# --------------------------------------------------------------------------- #
# 主窗口
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# 主题：每个控件按「角色」登记配色，切换主题时原地重绘
# --------------------------------------------------------------------------- #
# role(背景)      : bg | panel | panel_alt | line | accent | accent_soft
# fg(前景)        : text | text_soft | muted | accent | accent_text | now | expired | done
def style_widget(widget: tk.Misc, palette: Dict[str, str], role: str = "", fg: str = "") -> None:
    """登记控件配色并立即应用。"""
    if role:
        widget._ds_role = role
    if fg:
        widget._ds_fg = fg
    apply_widget_style(widget, palette)


def apply_widget_style(widget: tk.Misc, palette: Dict[str, str]) -> None:
    role = getattr(widget, "_ds_role", "")
    fg_key = getattr(widget, "_ds_fg", "")
    if not role and not fg_key:
        return
    options: Dict[str, str] = {}
    if role:
        options["bg" if isinstance(widget, (tk.Tk, tk.Toplevel, tk.Frame, tk.Label, tk.Canvas)) else "background"] = palette.get(role, palette["panel"])
    if fg_key:
        options["fg"] = palette.get(fg_key, palette["text"])
    try:
        widget.configure(**options)
        if isinstance(widget, tk.Text):
            widget.configure(insertbackground=palette["text"])
    except Exception:
        pass


def restyle_tree(widget: tk.Misc, palette: Dict[str, str]) -> None:
    for child in widget.winfo_children():
        apply_widget_style(child, palette)
        restyle_tree(child, palette)


class TaskApp:
    REFRESH_MS = 15000

    def __init__(self, root: tk.Tk, store: TaskStore, settings: Settings,
                 silent_start: bool = False, history: Optional[HistoryStore] = None):
        self.root = root
        self.store = store
        self.settings = settings
        self.silent_start = silent_start
        self.history = history or HistoryStore(store.dir)
        if history is None:
            self.history.load()
        self._popup_open: Dict[str, object] = {}
        self._menu_vars: List[tk.BooleanVar] = []
        self._last_alert: Optional[datetime] = None
        self._history_window: Optional[HistoryWindow] = None

        # _setup_style() 内部会调用 apply_theme()，界面在那里构建，这里不要再建一次
        self._setup_style()
        self._bind_keys()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self._after_ids: List[str] = []
        self._closed = False
        self._schedule(300, self._startup_report)
        self._schedule(1000, self._tick)

    def _schedule(self, delay_ms: int, callback) -> None:
        """登记的定时任务，退出时统一取消（避免 Tcl 报 invalid command name）。"""
        if self._closed:
            return
        try:
            self._after_ids.append(self.root.after(delay_ms, callback))
        except tk.TclError:
            self._closed = True

    def _cancel_timers(self) -> None:
        for after_id in self._after_ids:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        self._after_ids.clear()

    # ------------------------------------------------------------------ #
    # 外观与布局
    # ------------------------------------------------------------------ #
    def theme(self) -> Dict[str, str]:
        return PALETTES["dark" if self.settings.dark_mode else "light"]

    def _preferred_theme(self, style: ttk.Style) -> str:
        """浅色模式优先用系统原生看着更协调的主题。"""
        available = set(style.theme_names())
        for name in ("vista", "winnative", "clam"):
            if name in available:
                return name
        return style.theme_use()

    def _setup_style(self) -> None:
        self.root.title(APP_TITLE)
        self.root.minsize(820, 540)
        self.root.geometry("940x660")
        icon = resource_path("app.ico")
        if icon.exists():
            try:
                self.root.iconbitmap(default=str(icon))
            except Exception:
                pass
        self.apply_theme()

    def apply_theme(self) -> None:
        """把当前配色应用到窗口与控件（深色下需要换用可自定义颜色的 ttk 主题）。"""
        p = self.palette = self.theme()
        style = ttk.Style()
        # Windows 原生 vista 主题不吃颜色配置，深色模式改用 clam
        wanted = "clam" if self.settings.dark_mode else self._preferred_theme(style)
        if getattr(self, "_ttk_theme", "") != wanted:
            try:
                style.theme_use(wanted)
                self._ttk_theme = wanted
            except Exception:
                pass

        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(10, 5),
                        background=p["panel_alt"], foreground=p["text"],
                        bordercolor=p["line"], lightcolor=p["panel_alt"], darkcolor=p["panel_alt"],
                        focuscolor=p["line"], relief="flat")
        style.map("TButton",
                  background=[("pressed", p["accent_soft"]), ("active", p["accent_soft"]),
                              ("disabled", p["panel_alt"])],
                  foreground=[("disabled", p["muted"])])
        style.configure("TEntry", fieldbackground=p["panel_alt"], foreground=p["text"],
                        insertcolor=p["text"], bordercolor=p["line"],
                        lightcolor=p["line"], darkcolor=p["line"])
        style.configure("TCombobox", fieldbackground=p["panel_alt"], foreground=p["text"],
                        background=p["panel_alt"], arrowcolor=p["text_soft"],
                        bordercolor=p["line"], lightcolor=p["line"], darkcolor=p["line"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", p["panel_alt"]), ("disabled", p["panel_alt"])],
                  foreground=[("readonly", p["text"]), ("disabled", p["muted"])],
                  background=[("readonly", p["panel_alt"])],
                  selectbackground=[("readonly", p["accent_soft"])],
                  selectforeground=[("readonly", p["text"])])
        style.configure("Treeview", font=("Microsoft YaHei UI", 10), rowheight=30,
                        background=p["panel"], fieldbackground=p["panel"], foreground=p["text"],
                        bordercolor=p["line"], borderwidth=0)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"),
                        background=p["panel_alt"], foreground=p["text_soft"], padding=(4, 6),
                        relief="flat", bordercolor=p["line"])
        style.map("Treeview.Heading", background=[("active", p["accent_soft"])])
        style.map("Treeview",
                  background=[("selected", p["sel_bg"])],
                  foreground=[("selected", p["sel_fg"])])
        style.configure("TCheckbutton", background=p["panel"], foreground=p["text"],
                        focuscolor=p["panel"], indicatorcolor=p["panel_alt"])
        style.map("TCheckbutton", background=[("active", p["panel"])],
                  foreground=[("disabled", p["muted"])],
                  indicatorcolor=[("selected", p["accent"]), ("!selected", p["panel_alt"])])
        style.configure("TRadiobutton", background=p["panel"], foreground=p["text"],
                        focuscolor=p["panel"], indicatorcolor=p["panel_alt"])
        style.map("TRadiobutton", background=[("active", p["panel"])],
                  foreground=[("disabled", p["muted"])],
                  indicatorcolor=[("selected", p["accent"]), ("!selected", p["panel_alt"])])
        style.configure("Vertical.TScrollbar", background=p["panel_alt"], troughcolor=p["bg"],
                        bordercolor=p["bg"], arrowcolor=p["text_soft"], relief="flat")
        style.map("Vertical.TScrollbar", background=[("active", p["accent_soft"])])
        style.configure("TSeparator", background=p["line"])

        self.root.configure(bg=p["bg"])
        if getattr(self, "_built", False):
            # 界面已经建好：原地重绘所有控件，避免销毁重建造成失效引用
            restyle_tree(self.root, p)
            self._configure_tree_tags()
            self._theme_button.configure(text="☀ 浅色" if self.settings.dark_mode else "🌙 深色")
            self.refresh()
            if self._history_window is not None and self._history_window.alive():
                self._history_window.apply_theme(p)
            return

        self._built = True
        self._empty_visible = False
        self._build_ui()
        self._configure_tree_tags()
        self._theme_button.configure(text="☀ 浅色" if self.settings.dark_mode else "🌙 深色")

    def _configure_tree_tags(self) -> None:
        p = self.palette
        self.tree.tag_configure("now", foreground=p["now"])
        self.tree.tag_configure("expired", foreground=p["expired"])
        self.tree.tag_configure("done", foreground=p["done"])
        self.tree.tag_configure("off", foreground=p["muted"])
        self.tree.tag_configure("odd", background=p["panel_alt"])
        self.tree.tag_configure("plain", background=p["panel"])

    def _build_ui(self) -> None:
        p = self.palette
        # 幂等保护：万一被调用两次，先清空旧控件，避免出现两套界面
        for child in self.root.winfo_children():
            child.destroy()

        def frame(parent: tk.Misc, role: str = "panel", **kw) -> tk.Frame:
            widget = tk.Frame(parent, bg=p[role], **kw)
            style_widget(widget, p, role=role)
            return widget

        def label(parent: tk.Misc, role: str = "panel", fg: str = "text", **kw) -> tk.Label:
            widget = tk.Label(parent, bg=p[role], fg=p[fg], **kw)
            style_widget(widget, p, role=role, fg=fg)
            return widget

        # 顶部标题栏
        header = frame(self.root, "panel", height=74)
        header.pack(fill="x")
        header.pack_propagate(False)

        left = frame(header, "panel")
        left.pack(side="left", padx=(20, 0))
        label(left, "panel", "text", text="每日任务提醒",
              font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w", pady=(14, 0))
        self.subtitle = label(left, "panel", "muted", text="", font=("Microsoft YaHei UI", 9))
        self.subtitle.pack(anchor="w")

        right = frame(header, "panel")
        right.pack(side="right", padx=(0, 20))
        top = frame(right, "panel")
        top.pack(anchor="e", pady=(10, 0))
        self._theme_button = ttk.Button(top, text="🌙 深色", width=9, command=self.toggle_dark_mode)
        self._theme_button.pack(side="right")
        self.clock_label = label(top, "panel", "text", text="", font=("Consolas", 22, "bold"))
        self.clock_label.pack(side="right", padx=(0, 10))
        self.date_label = label(right, "panel", "muted", text="", font=("Microsoft YaHei UI", 9))
        self.date_label.pack(anchor="e")

        frame(self.root, "line", height=1).pack(fill="x")

        # 工具条
        bar = frame(self.root, "panel")
        bar.pack(fill="x", padx=12, pady=(10, 6))

        ttk.Button(bar, text="＋ 新建任务", command=self.add_task).pack(side="left")
        ttk.Button(bar, text="编辑", width=7, command=self.edit_task).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="今日打卡", width=9, command=self.toggle_done).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="完成记录", width=9, command=self.show_history).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="启用/停用", width=10, command=self.toggle_enabled).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="删除", width=7, command=self.delete_task).pack(side="left", padx=(6, 0))

        self.menu_button = ttk.Button(bar, text="系统 ▾", width=9, command=self._show_menu)
        self.menu_button.pack(side="right")

        search_box = frame(bar, "panel")
        search_box.pack(side="right", padx=(0, 10))
        label(search_box, "panel", "muted", text="搜索",
              font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(0, 4))
        if not hasattr(self, "search_var"):
            self.search_var = tk.StringVar()
            self.search_var.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(search_box, textvariable=self.search_var, width=16).pack(side="left", ipady=2)
        ttk.Button(search_box, text="✕", width=3,
                   command=lambda: self.search_var.set("")).pack(side="left", padx=(3, 0))

        # 列表
        wrap = frame(self.root, "bg")
        wrap.pack(fill="both", expand=True, padx=12)

        columns = ("status", "title", "kind", "schedule", "next")
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
        headings = {
            "status": ("状态", 110, "w"),
            "title": ("任务名称", 260, "w"),
            "kind": ("类型", 88, "center"),
            "schedule": ("时间安排", 168, "w"),
            "next": ("下次提醒", 120, "w"),
        }
        for key, (text, width, anchor) in headings.items():
            self.tree.heading(key, text=text, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "title"))

        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.empty_label = label(
            wrap, "bg", "muted",
            text="还没有任务，点左上角「＋ 新建任务」开始吧\n\n"
                 "· 每日循环：每天到点提醒，可限定星期\n"
                 "· 一次性：指定日期和时间，只提醒一次",
            justify="center", font=("Microsoft YaHei UI", 11))
        self._empty_visible = False

        self.tree.bind("<Double-1>", lambda _e: self.edit_task())
        self.tree.bind("<Return>", lambda _e: self.edit_task())
        self.tree.bind("<space>", lambda _e: self.toggle_done())
        self.tree.bind("<Delete>", lambda _e: self.delete_task())
        self.tree.bind("<Button-3>", self._popup_menu)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.context = tk.Menu(self.root, tearoff=0, bg=p["panel"], fg=p["text"],
                               activebackground=p["accent"], activeforeground="#ffffff",
                               bd=0, relief="flat")
        self.context.add_command(label="编辑任务", command=self.edit_task)
        self.context.add_command(label="今日打卡 / 取消", command=self.toggle_done)
        self.context.add_command(label="启用 / 停用", command=self.toggle_enabled)
        self.context.add_separator()
        self.context.add_command(label="查看该任务的完成记录", command=self.show_history_for_selected)
        self.context.add_separator()
        self.context.add_command(label="稍后 5 分钟提醒", command=lambda: self.snooze_selected(5))
        self.context.add_command(label="稍后 30 分钟提醒", command=lambda: self.snooze_selected(30))
        self.context.add_separator()
        self.context.add_command(label="立即提醒一次（测试）", command=self.test_remind_selected)
        self.context.add_command(label="删除任务", command=self.delete_task)

        # 底部状态栏
        footer = frame(self.root, "panel")
        footer.pack(fill="x", pady=(8, 0))
        frame(footer, "line", height=1).pack(fill="x")
        inner = frame(footer, "panel")
        inner.pack(fill="x", padx=14, pady=7)
        self.status_label = label(inner, "panel", "text_soft", text="", font=("Microsoft YaHei UI", 9))
        self.status_label.pack(side="left")
        self.streak_label = label(inner, "panel", "muted", text="", font=("Microsoft YaHei UI", 9))
        self.streak_label.pack(side="left", padx=(14, 0))
        self.tip_label = label(inner, "panel", "muted", text="× 关闭窗口只是最小化到后台，提醒继续运行",
                               font=("Microsoft YaHei UI", 9))
        self.tip_label.pack(side="right")

    def _on_select(self, _event: tk.Event) -> None:
        self._last_selected = self.selected_id()

    def _bind_keys(self) -> None:
        def safe(action) -> Callable[[tk.Event], str]:
            """包一层，窗口已销毁时不再抛出 Tcl 错误。"""
            def handler(_event: tk.Event) -> str:
                try:
                    action()
                except tk.TclError:
                    pass
                return "break"
            return handler

        self.root.bind("<Control-n>", safe(self.add_task))
        self.root.bind("<Control-d>", safe(self.toggle_enabled))
        self.root.bind("<Control-h>", safe(self.show_history))
        self.root.bind("<Control-l>", safe(self.toggle_dark_mode))
        self.root.bind("<Control-r>", safe(lambda: self.tick(force=True)))
        self.root.bind("<F5>", safe(self.refresh))
        self.root.bind("<Escape>", safe(self.hide_window))

    def _show_menu(self) -> None:
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_checkbutton(label="一次性任务提醒后视为已完成", onvalue=True, offvalue=False,
                             variable=self._bool_var(self.settings.one_time_auto_done),
                             command=lambda: self._set_auto_done(not self.settings.one_time_auto_done))
        menu.add_checkbutton(label="开机自动启动", onvalue=True, offvalue=False,
                             variable=self._bool_var(self.settings.autostart),
                             command=self.toggle_autostart)
        menu.add_checkbutton(label="同时发送 Windows 系统通知", onvalue=True, offvalue=False,
                             variable=self._bool_var(self.settings.windows_toast),
                             command=self.toggle_windows_toast)
        menu.add_checkbutton(label="提醒时播放提示音", onvalue=True, offvalue=False,
                             variable=self._bool_var(self.settings.sound),
                             command=self.toggle_sound)
        menu.add_checkbutton(label="列表显示已完成任务", onvalue=True, offvalue=False,
                             variable=self._bool_var(self.settings.show_finished),
                             command=self.toggle_show_finished)
        menu.add_checkbutton(label="深色模式（护眼）", onvalue=True, offvalue=False,
                             variable=self._bool_var(self.settings.dark_mode),
                             command=self.toggle_dark_mode)
        menu.add_separator()
        menu.add_command(label="完成记录 / 打卡历史…", command=self.show_history)
        menu.add_separator()
        menu.add_command(label="导入任务…", command=self.import_tasks)
        menu.add_command(label="导出任务…", command=self.export_tasks)
        menu.add_command(label="打开数据目录", command=self.open_data_dir)
        menu.add_separator()
        menu.add_command(label="最小化到后台", command=self.hide_window)
        menu.add_command(label="使用说明 / 快捷键", command=self.show_about)
        menu.add_separator()
        menu.add_command(label="退出程序", command=self.quit_app)

        x = self.menu_button.winfo_rootx()
        y = self.menu_button.winfo_rooty() + self.menu_button.winfo_height() + 4
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _bool_var(self, value: bool) -> tk.BooleanVar:
        """保存引用，避免被垃圾回收导致菜单勾选状态异常。"""
        var = tk.BooleanVar(master=self.root, value=bool(value))
        self._menu_vars.append(var)
        self._menu_vars = self._menu_vars[-10:]
        return var

    # ------------------------------------------------------------------ #
    # 刷新
    # ------------------------------------------------------------------ #
    def visible_tasks(self) -> List[Task]:
        keyword = self.search_var.get().strip().lower()
        items = self.store.sorted_tasks()
        result = []
        for task in items:
            if keyword and keyword not in task.title.lower() and keyword not in (task.notes or "").lower():
                continue
            if not self.settings.show_finished and task.completed_today():
                continue
            result.append(task)
        return result

    def refresh(self) -> None:
        selected = self.selected_id()
        self.tree.delete(*self.tree.get_children())
        for index, task in enumerate(self.visible_tasks()):
            status = task.status()
            label, color_key = STATUS_META.get(status, ("—", "text_soft"))
            tags = []
            if status in ("now", "soon"):
                tags.append("now")
            elif status == "expired":
                tags.append("expired")
            elif status in ("daily_done", "done_once"):
                tags.append("done")
            elif status == "off":
                tags.append("off")
            tags.append("odd" if index % 2 else "plain")
            if task.snooze_until:
                next_text = "已延后"
            else:
                next_text = task.next_text()
            self.tree.insert(
                "", "end", iid=task.tid,
                values=(label, task.title, KIND_META.get(task.kind, task.kind),
                        task.schedule_text(), next_text),
                tags=tuple(tags),
            )
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
        self._update_empty_hint()
        self._update_status()

    def _update_empty_hint(self) -> None:
        """列表为空时显示引导文字。"""
        should_show = not self.tree.get_children()
        if should_show and not self._empty_visible:
            self.empty_label.place(relx=0.5, rely=0.42, anchor="center")
            self._empty_visible = True
        elif not should_show and self._empty_visible:
            self.empty_label.place_forget()
            self._empty_visible = False

    def _update_status(self) -> None:
        stats = self.store.stats()
        self.status_label.configure(
            text=f"共 {stats['total']} 个任务　·　今日待办 {stats['due']} 项　·　已完成 {stats['finished']} 项　·　"
                 f"剩余 {stats['pending']} 项"
        )
        summary = self.history.summary()
        streak = summary["streak"]
        self.streak_label.configure(
            text=f"累计打卡 {summary['total']} 次　·　今天 {summary['today']} 次　·　"
                 f"连续 {streak} 天（最长 {summary['best_streak']} 天）"
        )
        if self.settings.autostart:
            warn = verify_launch_target()
            self.subtitle.configure(text="开机自启：已开启" + (f"（{warn}）" if warn else ""),
                                    fg=self.palette["expired"] if warn else self.palette["done"])
        else:
            self.subtitle.configure(text="开机自启：未开启", fg=self.palette["muted"])

    def _sort_by(self, key: str) -> None:
        # 说明：列表默认按“状态 + 时间”排序，点表头只做一次简单重排
        order = {"status": lambda t: t.status(), "title": lambda t: t.title.lower(),
                 "kind": lambda t: t.kind, "schedule": lambda t: t.time, "next": lambda t: t.next_text()}
        if key not in order:
            return
        self.store.tasks.sort(key=order[key])
        self.refresh()

    def _tick(self) -> None:
        try:
            now = datetime.now()
            self.clock_label.configure(text=now.strftime("%H:%M:%S"))
            weekday = "一二三四五六日"[now.weekday()]
            self.date_label.configure(text=now.strftime("%Y-%m-%d") + f"　周{weekday}")
            self._check_show_signal()
            self.tick()
        except tk.TclError:
            self._closed = True
            return          # 窗口已销毁，停止定时器
        self._schedule(1000, self._tick)

    def _check_show_signal(self) -> None:
        """用户再次双击图标时，把在后台驻留的窗口显示出来。"""
        if self.root.state() == "normal":
            return          # 已经显示着，不用处理
        if consume_show_signal(self.store.dir):
            self.show_window()

    def tick(self, force: bool = False) -> None:
        today = date.today()
        fired_any = False
        for task in list(self.store.tasks):
            key = task.fire_key(today)
            if not key:
                continue
            slot = (task.tid, key)          # 同一时刻的多个任务各自独立弹窗
            if slot in self._popup_open:
                continue
            task.mark_fired(key)
            fired_any = True
            self._popup_open[slot] = True
            self._remind(task, key)
        if fired_any:
            self.store.prune_fired()
            self.store.save()
            self.refresh()

    def _remind(self, task: Task, key: str) -> None:
        detail = task.schedule_text()
        if task.notes:
            detail += "\n" + task.notes
        self._show_alert(task.title, detail)
        slot = (task.tid, key)

        def forget() -> None:
            self._popup_open.pop(slot, None)

        def on_snooze() -> None:
            task.snooze(key, 5)
            self.store.save()
            self.refresh()
            forget()

        def on_done() -> None:
            self.mark_done(task, source="card")
            forget()

        def on_open() -> None:
            self.show_window()
            forget()

        ToastPopup(self.root, task.title, detail, accent=self.palette["accent"],
                   on_snooze=on_snooze,
                   on_done=on_done,
                   on_open=on_open)

        if self.settings.one_time_auto_done and not task.is_daily:
            self.mark_done(task)

    def _show_alert(self, title: str, message: str) -> None:
        now = datetime.now()
        if self.settings.sound:
            play_sound()
        if self.settings.windows_toast and (self._last_alert is None or (now - self._last_alert).total_seconds() > 1.0):
            show_windows_toast(f"任务提醒：{title}", message.replace("\n", "  "))
        self._last_alert = now

    # ------------------------------------------------------------------ #
    # 任务操作
    # ------------------------------------------------------------------ #
    def selected_id(self) -> str:
        selection = self.tree.selection()
        return selection[0] if selection else ""

    def selected_task(self) -> Optional[Task]:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.store.get(selection[0])

    def add_task(self) -> None:
        dialog = TaskDialog(self.root, palette=self.palette)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        self.store.add(dialog.result)
        self.store.save()
        self.refresh()
        self.tree.selection_set(dialog.result.tid)
        self.tree.see(dialog.result.tid)
        self.tick()

    def edit_task(self) -> None:
        task = self.selected_task()
        if task is None:
            messagebox.showinfo("未选择任务", "请先在列表中选择一个任务。", parent=self.root)
            return
        dialog = TaskDialog(self.root, task, palette=self.palette)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return
        self.store.save()
        self.refresh()
        self.tick()

    def delete_task(self) -> None:
        task = self.selected_task()
        if task is None:
            return
        if not messagebox.askyesno("删除任务", f"确定删除「{task.title}」吗？", parent=self.root):
            return
        self.store.remove(task.tid)
        self.store.save()
        self.refresh()

    def mark_done(self, task: Task, source: str = "list") -> None:
        """打卡：更新任务状态，并写入一条完成记录。"""
        today = date.today()
        if task.is_daily:
            task.last_done = today.strftime(DATE_FMT)
        else:
            task.done = True
        task.snooze_until = None
        self.record_done(task, source)
        self.store.save()
        self.refresh()
        self._update_status()

    def record_done(self, task: Task, source: str = "list") -> None:
        """写入完成记录（同名任务重复打卡会各留一条）。"""
        self.history.add(
            title=task.title,
            kind=task.kind,
            schedule=task.schedule_text(),
            source=source,
            notes=task.notes,
            task_id=task.tid,
        )
        self.history.save()

    def toggle_done(self) -> None:
        task = self.selected_task()
        if task is None:
            messagebox.showinfo("未选择任务", "请先在列表中选择一个任务。", parent=self.root)
            return
        today = date.today()
        if task.is_daily:
            marking = task.last_done != today.strftime(DATE_FMT)
            task.last_done = today.strftime(DATE_FMT) if marking else ""
        else:
            marking = not task.done
            task.done = marking
        task.snooze_until = None
        if marking:
            self.record_done(task, "list")
        else:
            self.history.remove_last_for_task(task.tid)
            self.history.save()
        self.store.save()
        self.refresh()
        self._update_status()

    def toggle_enabled(self) -> None:
        task = self.selected_task()
        if task is None:
            return
        task.enabled = not task.enabled
        if task.enabled:
            task.snooze_until = None
        self.store.save()
        self.refresh()

    def snooze_selected(self, minutes: int) -> None:
        task = self.selected_task()
        if task is None:
            return
        task.snooze_until = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")
        task.fired = [k for k in task.fired if k != task.occurrence_key(date.today())]
        self.store.save()
        self.refresh()

    def test_remind_selected(self) -> None:
        task = self.selected_task()
        if task is None:
            return
        detail = task.schedule_text() + (("\n" + task.notes) if task.notes else "")
        self._show_alert(task.title, detail)
        ToastPopup(self.root, task.title, detail, accent=self.palette["accent"])

    def _popup_menu(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        try:
            self.context.tk_popup(event.x_root, event.y_root)
        finally:
            self.context.grab_release()

    # ------------------------------------------------------------------ #
    # 完成记录
    # ------------------------------------------------------------------ #
    def show_history(self) -> None:
        if self._history_window is not None and self._history_window.alive():
            self._history_window.lift()
            self._history_window.refresh()
            return
        self._history_window = HistoryWindow(self.root, self.history, self.palette)

    def show_history_for_selected(self) -> None:
        task = self.selected_task()
        if task is None:
            self.show_history()
            return
        self.show_history()
        if self._history_window is not None:
            self._history_window.focus_task(task.title)

    # ------------------------------------------------------------------ #
    # 深色模式
    # ------------------------------------------------------------------ #
    def toggle_dark_mode(self, value: Optional[bool] = None) -> None:
        self.settings.dark_mode = (not self.settings.dark_mode) if value is None else bool(value)
        self.settings.save()
        self.apply_theme()
        self.refresh()

    # ------------------------------------------------------------------ #
    # 系统功能
    # ------------------------------------------------------------------ #
    def toggle_autostart(self) -> None:
        target = not self.settings.autostart
        ok, info = set_autostart(target)
        if not ok:
            messagebox.showerror("设置失败", f"无法修改开机启动项：{info}", parent=self.root)
            return
        self.settings.autostart = target
        self.settings.save()
        self._update_status()
        messagebox.showinfo("开机自启",
                            ("已开启开机自动启动。\n" + info) if target else "已关闭开机自动启动。",
                            parent=self.root)

    def toggle_windows_toast(self) -> None:
        self.settings.windows_toast = not self.settings.windows_toast
        self.settings.save()

    def toggle_sound(self) -> None:
        self.settings.sound = not self.settings.sound
        self.settings.save()

    def toggle_show_finished(self) -> None:
        self.settings.show_finished = not self.settings.show_finished
        self.settings.save()
        self.refresh()

    def _set_auto_done(self, value: bool) -> None:
        self.settings.one_time_auto_done = bool(value)
        self.settings.save()

    def import_tasks(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="导入任务",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            items = raw.get("tasks") if isinstance(raw, dict) else raw
            count = 0
            for item in items or []:
                if isinstance(item, dict):
                    task = Task.from_dict(item)
                    task.tid = Task().tid
                    task.fired = []
                    self.store.add(task)
                    count += 1
            self.store.save()
            self.refresh()
            messagebox.showinfo("导入完成", f"成功导入 {count} 个任务。", parent=self.root)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.root)

    def export_tasks(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root, title="导出任务", defaultextension=".json",
            initialfile=f"tasks-{date.today().strftime('%Y%m%d')}.json",
            filetypes=[("JSON 文件", "*.json")])
        if not path:
            return
        try:
            payload = {
                "version": 1,
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "tasks": [t.to_dict() for t in self.store.tasks],
            }
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            messagebox.showinfo("导出完成", f"已导出到：\n{path}", parent=self.root)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self.root)

    def open_data_dir(self) -> None:
        import os
        try:
            os.startfile(self.store.dir)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc), parent=self.root)

    def show_about(self) -> None:
        messagebox.showinfo("使用说明", ABOUT_TEXT, parent=self.root)

    # ------------------------------------------------------------------ #
    # 窗口生命周期
    # ------------------------------------------------------------------ #
    def hide_window(self) -> None:
        self.root.withdraw()

    def show_window(self) -> None:
        """把主窗口显示出来并置前（从后台驻留状态唤回）。"""
        try:
            self.root.deiconify()
            if self.root.state() != "normal":
                self.root.state("normal")
            self.root.update_idletasks()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self._drop_topmost())
            self.root.focus_force()
        except tk.TclError:
            pass

    def _drop_topmost(self) -> None:
        """短暂置顶后取消，避免一直压住别的窗口。"""
        try:
            self.root.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _startup_report(self) -> None:
        try:
            self.settings.autostart = self.settings.autostart or False
            self.refresh()
            self.tick(force=True)
            if self.silent_start:
                self.hide_window()
            if self.store.load_error:
                messagebox.showwarning("任务文件异常",
                                       self.store.load_error + "\n\n已备份原文件并重新开始。",
                                       parent=self.root)
        except tk.TclError:
            return          # 窗口已关闭（例如测试中提前退出）

    def quit_app(self) -> None:
        self._closed = True
        self._cancel_timers()
        try:
            self.store.save()
            self.settings.save()
            self.history.save()
        except Exception:
            pass
        self.root.destroy()
