# -*- coding: utf-8 -*-
"""完成记录（打勾记录）：每次打卡都会留下一条带时间的记录。"""
from __future__ import annotations

import csv
import json
import os
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

STAMP_FMT = "%Y-%m-%d %H:%M:%S"
DAY_FMT = "%Y-%m-%d"

KIND_NAMES = {"daily": "每日循环", "once": "一次性"}

# 来源标记
SOURCE_TEXT = {
    "list": "列表打卡",
    "card": "提醒卡片",
    "auto": "系统自动",
    "undo": "撤销打卡",
}

MAX_RECORDS = 20000
KEEP_DAYS = 400


@dataclass
class Record:
    title: str = ""
    kind: str = "daily"
    schedule: str = ""          # 计划时间，例如 09:00 · 工作日
    stamp: str = ""             # 完成时间 YYYY-MM-DD HH:MM:SS
    source: str = "list"
    notes: str = ""
    task_id: str = ""

    # ---------------- 序列化 ---------------- #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "kind": self.kind,
            "schedule": self.schedule,
            "stamp": self.stamp,
            "source": self.source,
            "notes": self.notes,
            "task_id": self.task_id,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> Optional["Record"]:
        stamp = str(raw.get("stamp") or "").strip()
        if not stamp:
            return None
        return cls(
            title=str(raw.get("title") or "未命名任务"),
            kind=str(raw.get("kind") or "daily"),
            schedule=str(raw.get("schedule") or ""),
            stamp=stamp,
            source=str(raw.get("source") or "list"),
            notes=str(raw.get("notes") or ""),
            task_id=str(raw.get("task_id") or ""),
        )

    # ---------------- 派生信息 ---------------- #
    @property
    def when(self) -> Optional[datetime]:
        for fmt in (STAMP_FMT, "%Y-%m-%d %H:%M", DAY_FMT):
            try:
                return datetime.strptime(self.stamp, fmt)
            except ValueError:
                continue
        return None

    @property
    def day(self) -> str:
        moment = self.when
        return moment.strftime(DAY_FMT) if moment else self.stamp[:10]

    @property
    def kind_text(self) -> str:
        return KIND_NAMES.get(self.kind, self.kind)

    @property
    def source_text(self) -> str:
        return SOURCE_TEXT.get(self.source, self.source)

    def is_late(self) -> Optional[bool]:
        """计划时间 vs 实际完成时间：True 表示晚于计划。"""
        moment = self.when
        if moment is None or not self.schedule:
            return None
        head = self.schedule.split("·")[0].strip()
        try:
            planned = datetime.strptime(head, "%H:%M").time()
        except ValueError:
            return None
        planned_dt = datetime.combine(moment.date(), planned)
        return moment > planned_dt + timedelta(minutes=1)

    def delay_text(self) -> str:
        moment = self.when
        if moment is None or not self.schedule:
            return ""
        head = self.schedule.split("·")[0].strip()
        try:
            planned = datetime.strptime(head, "%H:%M").time()
        except ValueError:
            return ""
        delta = (moment - datetime.combine(moment.date(), planned)).total_seconds()
        mins = int(abs(delta) // 60)
        if mins <= 1:
            return "准点"
        if delta > 0:
            if mins < 60:
                return f"晚 {mins} 分钟"
            return f"晚 {mins // 60} 小时{mins % 60} 分"
        if mins < 60:
            return f"早 {mins} 分钟"
        return f"早 {mins // 60} 小时{mins % 60} 分"


# --------------------------------------------------------------------------- #
# 记录仓库
# --------------------------------------------------------------------------- #
class HistoryStore:
    def __init__(self, data_dir: Optional[Path] = None):
        from .tasks import default_data_dir
        self.dir = Path(data_dir) if data_dir else default_data_dir()
        self.path = self.dir / "history.json"
        self.records: List[Record] = []
        self.load_error = ""

    # ---------------- 读写 ---------------- #
    def load(self) -> None:
        self.records = []
        self.load_error = ""
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.load_error = f"完成记录无法解析：{exc}"
            try:
                shutil.copy2(self.path, self.path.with_suffix(".bad.json"))
            except Exception:
                pass
            return
        items = raw.get("records") if isinstance(raw, dict) else raw
        for item in items or []:
            if isinstance(item, dict):
                record = Record.from_dict(item)
                if record is not None:
                    self.records.append(record)
        self.prune()

    def save(self) -> bool:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": datetime.now().strftime(STAMP_FMT),
            "records": [r.to_dict() for r in self.records],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.path)
            return True
        except Exception:
            pass
        try:
            self.path.write_text(text, encoding="utf-8")
            return True
        except Exception:
            return False

    def prune(self) -> None:
        """只保留最近 KEEP_DAYS 天、最多 MAX_RECORDS 条。"""
        cutoff = (date.today() - timedelta(days=KEEP_DAYS)).strftime(DAY_FMT)
        self.records = [r for r in self.records if r.day >= cutoff]
        if len(self.records) > MAX_RECORDS:
            self.records = self.records[-MAX_RECORDS:]

    # ---------------- 增删 ---------------- #
    def add(self, title: str, kind: str = "daily", schedule: str = "",
            source: str = "list", notes: str = "", task_id: str = "",
            stamp: Optional[datetime] = None) -> Record:
        moment = stamp or datetime.now()
        record = Record(
            title=title, kind=kind, schedule=schedule, source=source,
            notes=notes, task_id=task_id, stamp=moment.strftime(STAMP_FMT),
        )
        self.records.append(record)
        self.prune()
        return record

    def remove_last_for_task(self, task_id: str) -> bool:
        """撤销打卡时删掉该任务最近一条记录。"""
        for index in range(len(self.records) - 1, -1, -1):
            if self.records[index].task_id == task_id:
                del self.records[index]
                return True
        return False

    def clear(self) -> int:
        count = len(self.records)
        self.records = []
        return count

    # ---------------- 查询 ---------------- #
    def query(self, days: int = 7, keyword: str = "", kind: str = "all") -> List[Record]:
        """按天数 / 关键词 / 类型筛选，按时间倒序。"""
        result: List[Record] = []
        cutoff = None
        if days > 0:
            cutoff = (date.today() - timedelta(days=days - 1)).strftime(DAY_FMT)
        keyword = keyword.strip().lower()
        for record in self.records:
            if cutoff and record.day < cutoff:
                continue
            if kind != "all" and record.kind != kind:
                continue
            if keyword and keyword not in record.title.lower() and keyword not in record.notes.lower():
                continue
            result.append(record)
        result.sort(key=lambda r: r.stamp, reverse=True)
        return result

    def count_on(self, day: Optional[date] = None) -> int:
        target = (day or date.today()).strftime(DAY_FMT)
        return sum(1 for r in self.records if r.day == target)

    def active_days(self) -> int:
        return len({r.day for r in self.records})

    def best_streak(self) -> int:
        """连续打卡天数（历史最长连续段）。"""
        days = sorted({r.day for r in self.records})
        if not days:
            return 0
        best = current = 1
        for prev, cur in zip(days, days[1:]):
            try:
                gap = (datetime.strptime(cur, DAY_FMT) - datetime.strptime(prev, DAY_FMT)).days
            except ValueError:
                continue
            current = current + 1 if gap == 1 else 1
            best = max(best, current)
        return best

    def current_streak(self) -> int:
        """当前连续打卡天数（允许今天还没打卡）。"""
        days = {r.day for r in self.records}
        if not days:
            return 0
        streak = 0
        cursor = date.today()
        if cursor.strftime(DAY_FMT) not in days:
            cursor -= timedelta(days=1)
        while cursor.strftime(DAY_FMT) in days:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def top_tasks(self, limit: int = 5, days: int = 30) -> List[tuple]:
        cutoff = (date.today() - timedelta(days=days - 1)).strftime(DAY_FMT)
        counter = Counter(r.title for r in self.records if r.day >= cutoff)
        return counter.most_common(limit)

    def daily_counts(self, days: int = 7) -> List[tuple]:
        """最近 N 天每天的完成数量，返回 [(日期, 数量), ...]，从早到晚。"""
        counts = Counter(r.day for r in self.records)
        today = date.today()
        out = []
        for offset in range(days - 1, -1, -1):
            day = (today - timedelta(days=offset)).strftime(DAY_FMT)
            out.append((day, counts.get(day, 0)))
        return out

    def summary(self) -> Dict[str, Any]:
        return {
            "total": len(self.records),
            "today": self.count_on(),
            "active_days": self.active_days(),
            "streak": self.current_streak(),
            "best_streak": self.best_streak(),
        }

    # ---------------- 导出 ---------------- #
    def export_csv(self, path: Path, records: Optional[List[Record]] = None) -> int:
        rows = records if records is not None else sorted(self.records, key=lambda r: r.stamp, reverse=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["完成时间", "任务名称", "类型", "计划安排", "提前/延后", "来源", "备注"])
            for record in rows:
                writer.writerow([
                    record.stamp, record.title, record.kind_text, record.schedule,
                    record.delay_text(), record.source_text, record.notes,
                ])
        return len(rows)

    def export_json(self, path: Path) -> int:
        payload = {
            "version": 1,
            "exported_at": datetime.now().strftime(STAMP_FMT),
            "records": [r.to_dict() for r in self.records],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(self.records)
