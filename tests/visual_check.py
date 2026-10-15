# -*- coding: utf-8 -*-
"""开发期辅助：示例数据 + 截图工作流说明。

截图做法（在沙箱里，Python 内部起 PowerShell 会被拦住，所以分两步）：

    # 1) 后台起一个常驻窗口
    python tests/hold_window.py --demo            # 浅色主界面
    python tests/hold_window.py --demo --dark     # 深色主界面
    python tests/hold_window.py --history --dark  # 深色完成记录
    python tests/hold_window.py --popups          # 提醒卡片
    python tests/hold_window.py --dialog --dark   # 编辑对话框

    # 2) 另一个终端里抓窗口
    pwsh -File tools/grab_window.ps1 -ProcessName python -Out shot.png -MinWidth 600

用法：
    python tests/visual_check.py            # 只打印上面的说明
    python tests/visual_check.py --demo     # 等价于直接跑 hold_window.py --demo
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from daily_task.tasks import Task, TaskStore  # noqa: E402

SHOTS = BASE / ".build" / "shots"


def demo_store(workdir: Path) -> TaskStore:
    """一批有代表性的示例任务，用于界面截图与人工检查。"""
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


GUIDE = """截图工作流（两步）：

  1) python tests/hold_window.py --demo            # 浅色主界面
     python tests/hold_window.py --demo --dark     # 深色主界面
     python tests/hold_window.py --history --dark  # 深色完成记录
     python tests/hold_window.py --popups          # 提醒卡片
     python tests/hold_window.py --dialog --dark   # 编辑对话框

  2) pwsh -File tools/grab_window.ps1 -ProcessName python -Out .build/shots/shot.png -MinWidth 600
"""


def main() -> int:
    if "--demo" in sys.argv or "--dark" in sys.argv or "--history" in sys.argv or "--popups" in sys.argv or "--dialog" in sys.argv:
        args = [sys.executable, str(BASE / "tests" / "hold_window.py")] + [a for a in sys.argv[1:]]
        return subprocess.call(args)
    print(GUIDE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
