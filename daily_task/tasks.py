# -*- coding: utf-8 -*-
"""任务数据模型与本地持久化（纯标准库）。"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Optional

WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]  # 索引 0 = 周一
ALL_WEEKDAYS = [0, 1, 2, 3, 4, 5, 6]

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"
FIRE_FMT = "%Y-%m-%d %H:%M"

DATA_DIR_NAME = "DailyTaskReminder"


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def default_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / DATA_DIR_NAME


def pad_weekdays(days: Optional[List[int]]) -> Optional[List[int]]:
    """None / 空列表 / 全选 都表示“每天”。"""
    if not days:
        return None
    clean = sorted({int(d) for d in days if 0 <= int(d) <= 6})
    if not clean or len(clean) == 7:
        return None
    return clean


def weekdays_text(days: Optional[List[int]]) -> str:
    days = pad_weekdays(days)
    if days is None:
        return "每天"
    if days == [0, 1, 2, 3, 4]:
        return "工作日"
    if days == [5, 6]:
        return "周末"
    return "周" + "、".join(WEEKDAY_NAMES[d] for d in days)


def valid_time(value: str) -> bool:
    try:
        datetime.strptime(value.strip(), TIME_FMT)
        return True
    except Exception:
        return False


def valid_date(value: str) -> bool:
    try:
        datetime.strptime(value.strip(), DATE_FMT)
        return True
    except Exception:
        return False


def human_delta(target: datetime, now: datetime) -> str:
    """把时间差写成人话：3 分钟后 / 已过 2 小时 / 明天 09:00。"""
    delta = target - now
    secs = delta.total_seconds()
    mins = int(abs(secs) // 60)
    same_day = target.date() == now.date()

    if secs < 0:
        if mins < 1:
            return "刚刚到点"
        if mins < 60:
            return f"已过 {mins} 分钟"
        if same_day:
            return f"已过 {mins // 60} 小时"
        return f"已过 {mins // 1440} 天"

    if mins < 1:
        return "即将开始"
    if mins < 60:
        return f"{mins} 分钟后"
    if same_day:
        return f"{mins // 60} 小时后"
    if target.date() == now.date() + timedelta(days=1):
        return "明天 " + target.strftime(TIME_FMT)
    return target.strftime("%m-%d %H:%M")


# --------------------------------------------------------------------------- #
# 任务
# --------------------------------------------------------------------------- #
@dataclass
class Task:
    title: str = "新任务"
    notes: str = ""
    kind: str = "daily"                 # daily | once
    time: str = "09:00"                 # HH:MM
    date: str = ""                      # kind == once 时使用
    weekdays: Optional[List[int]] = None  # None = 每天；仅 daily 有效
    enabled: bool = True
    done: bool = False                  # 一次性任务是否已完成
    last_done: str = ""                 # 上次打卡日期 YYYY-MM-DD
    created: str = field(default_factory=lambda: datetime.now().strftime(FIRE_FMT))
    fired: List[str] = field(default_factory=list)   # 已经提醒过的时刻
    snooze_until: Optional[str] = None               # 稍后提醒到某时刻
    tid: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # ---------------- 序列化 ---------------- #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.tid,
            "title": self.title,
            "notes": self.notes,
            "kind": self.kind,
            "time": self.time,
            "date": self.date,
            "weekdays": self.weekdays,
            "enabled": self.enabled,
            "done": self.done,
            "last_done": self.last_done,
            "created": self.created,
            "fired": self.fired,
            "snooze_until": self.snooze_until,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Task":
        kind = raw.get("kind") if raw.get("kind") in ("daily", "once") else "daily"
        time_text = str(raw.get("time") or "09:00").strip()
        if not valid_time(time_text):
            time_text = "09:00"
        date_text = str(raw.get("date") or "").strip()
        if not valid_date(date_text):
            date_text = ""
        fired = [str(x) for x in (raw.get("fired") or []) if isinstance(x, (str, int))]
        return cls(
            title=str(raw.get("title") or "未命名任务"),
            notes=str(raw.get("notes") or ""),
            kind=kind,
            time=time_text,
            date=date_text,
            weekdays=pad_weekdays(raw.get("weekdays")),
            enabled=bool(raw.get("enabled", True)),
            done=bool(raw.get("done", False)),
            last_done=str(raw.get("last_done") or ""),
            created=str(raw.get("created") or datetime.now().strftime(FIRE_FMT)),
            fired=fired,
            snooze_until=raw.get("snooze_until") or None,
            tid=str(raw.get("id") or uuid.uuid4().hex[:12]),
        )

    # ---------------- 语义 ---------------- #
    @property
    def is_daily(self) -> bool:
        return self.kind == "daily"

    def time_obj(self) -> dtime:
        return datetime.strptime(self.time, TIME_FMT).time()

    def date_obj(self) -> Optional[date]:
        if self.is_daily or not self.date:
            return None
        return datetime.strptime(self.date, DATE_FMT).date()

    def schedule_text(self) -> str:
        if self.is_daily:
            return f"{self.time} · {weekdays_text(self.weekdays)}"
        base = f"{self.date or '未设置日期'} {self.time}"
        return base

    def _active_today(self, today: date) -> bool:
        if not self.is_daily:
            return True
        days = pad_weekdays(self.weekdays)
        if days is None:
            return True
        return today.weekday() in days

    def reminder_datetime(self, today: date) -> Optional[datetime]:
        """今天的提醒时刻（一次性任务若不在今天则返回 None）。"""
        if self.is_daily:
            if not self._active_today(today):
                return None
            return datetime.combine(today, self.time_obj())
        target = self.date_obj()
        if target is None or target != today:
            return None
        return datetime.combine(target, self.time_obj())

    def occurrence_key(self, today: date) -> str:
        return datetime.combine(today, self.time_obj()).strftime(FIRE_FMT)

    def completed_today(self, today: Optional[date] = None) -> bool:
        today = today or date.today()
        if self.is_daily:
            return self.last_done == today.strftime(DATE_FMT)
        return self.done

    def fire_key(self, today: date) -> Optional[str]:
        """到点需要提醒时返回该次提醒的 key，否则 None。"""
        if not self.enabled:
            return None
        today = today or date.today()
        now = datetime.now()

        target: Optional[datetime] = None
        if self.is_daily:
            if not self._active_today(today):
                return None
            if self.last_done == today.strftime(DATE_FMT):
                return None
            when = datetime.combine(today, self.time_obj())
            if now < when - timedelta(seconds=20):
                return None                       # 还没到点
            if now > when + timedelta(minutes=8):
                return None                       # 错过太久，标记为“已错过”
            target = when
        else:
            if not self.date or self.done:
                return None
            when = datetime.combine(self.date_obj(), self.time_obj())
            if now < when - timedelta(seconds=20):
                return None
            target = when                          # 一次性任务允许补提醒

        key = target.strftime(FIRE_FMT)
        if key in self.fired:
            return None
        if self.snooze_until:
            try:
                if now < datetime.strptime(self.snooze_until, FIRE_FMT):
                    return None
            except Exception:
                self.snooze_until = None
        return key

    def mark_fired(self, key: str) -> None:
        if key not in self.fired:
            self.fired.append(key)
        self.fired = self.fired[-8:]
        self.snooze_until = None

    def snooze(self, key: str, minutes: int = 5) -> None:
        """稍后提醒：把这次提醒挪到 N 分钟之后。"""
        if key in self.fired:
            self.fired.remove(key)
        self.snooze_until = (datetime.now() + timedelta(minutes=minutes)).strftime(FIRE_FMT)

    # ---------------- 状态 ---------------- #
    def status(self, today: Optional[date] = None) -> str:
        """返回：done / daily_done / now / soon / waiting / done_once / expired / off"""
        today = today or date.today()
        if not self.enabled:
            return "off"
        if self.completed_today(today):
            return "daily_done" if self.is_daily else "done_once"
        if self.is_daily:
            when = self.reminder_datetime(today)
            if when is None:
                return "waiting"                  # 今天不轮到这个任务
            now = datetime.now()
            if now >= when:
                return "now" if now <= when + timedelta(minutes=8) else "expired"
            return "soon" if when - now <= timedelta(hours=1) else "waiting"
        target = self.date_obj()
        if target is None:
            return "now"
        when = datetime.combine(target, self.time_obj())
        now = datetime.now()
        if now >= when:
            return "now" if now <= when + timedelta(minutes=8) else "expired"
        return "soon" if when - now <= timedelta(hours=24) else "waiting"

    def next_text(self, today: Optional[date] = None) -> str:
        today = today or date.today()
        now = datetime.now()
        if not self.enabled:
            return "已停用"
        if self.completed_today(today):
            return "今日已完成" if self.is_daily else "已完成"
        if self.is_daily:
            for offset in range(0, 8):
                day = today + timedelta(days=offset)
                if not self._active_today(day):
                    continue
                when = datetime.combine(day, self.time_obj())
                if offset > 0 or when >= now - timedelta(minutes=8):
                    return human_delta(when, now)
            return "—"
        target = self.date_obj()
        if target is None:
            return "未设置日期"
        when = datetime.combine(target, self.time_obj())
        if now > when + timedelta(minutes=8):
            return "已过期（" + human_delta(when, now) + "）"
        return human_delta(when, now)


# --------------------------------------------------------------------------- #
# 仓库
# --------------------------------------------------------------------------- #
class TaskStore:
    def __init__(self, data_dir: Optional[Path] = None):
        self.dir = Path(data_dir) if data_dir else default_data_dir()
        self.path = self.dir / "tasks.json"
        self.tasks: List[Task] = []
        self.load_error: str = ""

    # ---------------- 读写 ---------------- #
    def load(self) -> None:
        self.tasks = []
        self.load_error = ""
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:                     # 损坏则备份，避免丢数据
            self.load_error = f"任务文件无法解析：{exc}"
            try:
                shutil.copy2(self.path, self.path.with_suffix(".bad.json"))
            except Exception:
                pass
            return
        items = raw.get("tasks") if isinstance(raw, dict) else raw
        for item in items or []:
            if isinstance(item, dict):
                self.tasks.append(Task.from_dict(item))

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": datetime.now().strftime(FIRE_FMT),
            "tasks": [t.to_dict() for t in self.tasks],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
            return
        except Exception:
            pass
        # 少数受限环境禁止新建临时文件，退化为直接覆盖（仍先备份）
        try:
            if self.path.exists():
                try:
                    shutil.copy2(self.path, self.path.with_suffix(".bak.json"))
                except Exception:
                    pass
            self.path.write_text(text, encoding="utf-8")
        except Exception as exc:
            raise OSError(f"无法写入任务文件 {self.path}：{exc}") from exc


    # ---------------- 增删改查 ---------------- #
    def add(self, task: Task) -> Task:
        self.tasks.append(task)
        return task

    def get(self, tid: str) -> Optional[Task]:
        for task in self.tasks:
            if task.tid == tid:
                return task
        return None

    def remove(self, tid: str) -> bool:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.tid != tid]
        return len(self.tasks) != before

    def sorted_tasks(self, today: Optional[date] = None) -> List[Task]:
        today = today or date.today()
        now = datetime.now()

        def sort_key(task: Task):
            status_rank = {
                "now": 0, "soon": 1, "waiting": 2, "expired": 3,
                "done_once": 4, "daily_done": 5, "off": 6,
            }.get(task.status(today), 5)
            if task.is_daily:
                base = task.reminder_datetime(today) or datetime.combine(today, task.time_obj())
                if base < now:
                    base += timedelta(days=1)
            else:
                target = task.date_obj() or today
                base = datetime.combine(target, task.time_obj())
            return (status_rank, base, task.title)

        return sorted(self.tasks, key=sort_key)

    def prune_fired(self, keep_days: int = 4) -> None:
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime(FIRE_FMT)
        for task in self.tasks:
            task.fired = [k for k in task.fired if k >= cutoff]

    # ---------------- 统计 ---------------- #
    def stats(self, today: Optional[date] = None) -> Dict[str, int]:
        today = today or date.today()
        active = [t for t in self.tasks if t.enabled]
        due_today = [t for t in active if t.is_daily and t._active_today(today)]
        due_today += [t for t in active if not t.is_daily and t.date_obj() == today]
        finished = [t for t in due_today if t.completed_today(today)]
        return {
            "total": len(self.tasks),
            "active": len(active),
            "due": len(due_today),
            "finished": len(finished),
            "pending": len(due_today) - len(finished),
        }
