# -*- coding: utf-8 -*-
"""启动方式测试：手动启动必须看得见窗口。

回归背景：曾经把「开机静默驻留」设置误用到所有启动方式上，
导致用户双击启动器后程序在后台起来了、却不显示窗口，看起来像「没反应」。

用法： python tests/launch_test.py
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from daily_task.history import HistoryStore  # noqa: E402
from daily_task.settings import (  # noqa: E402
    SHOW_SIGNAL_NAME,
    Settings,
    consume_show_signal,
    launch_command,
    signal_show_window,
)
from daily_task.tasks import Task, TaskStore  # noqa: E402
from daily_task.ui import TaskApp  # noqa: E402

WORK = BASE / ".build" / "launch-data"


def reset() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    for item in WORK.iterdir():
        if item.is_file():
            item.unlink()
    return WORK


def build_settings() -> Settings:
    settings = Settings.load(WORK)
    settings.windows_toast = False
    settings.sound = False
    settings.dark_mode = False
    # 关键：模拟用户已经勾选过「开机自动启动」
    settings.autostart = True
    settings.save()
    return settings


def make_app(root: tk.Tk, silent: bool) -> TaskApp:
    store = TaskStore(WORK)
    store.add(Task(title="喝水", kind="daily", time="09:00"))
    store.save()
    history = HistoryStore(WORK)
    history.load()
    app = TaskApp(root, store, build_settings(), silent_start=silent, history=history)
    root.update()
    return app


def main() -> int:
    reset()

    # ---------- 1) 开机自启命令必须带 --silent ----------
    normal = launch_command()
    auto = launch_command(silent=True)
    assert "--silent" not in normal, f"普通启动命令不应带 --silent：{normal}"
    assert auto.endswith("--silent"), f"自启命令应带 --silent：{auto}"
    print("[i] 普通启动命令:", normal)
    print("[i] 开机自启命令:", auto)

    # ---------- 2) 勾选过自启，手动启动（不带 --silent）仍要显示窗口 ----------
    root = tk.Tk()
    app = make_app(root, silent=False)
    assert app.settings.autostart is True, "前置条件：已开启自启"
    assert app.silent_start is False, "手动启动不应静默"
    root.deiconify()
    root.update()
    state = root.state()
    assert state == "normal", f"手动启动时窗口应为 normal，实际 {state}"
    app.quit_app()
    print("[i] 勾选过自启 + 手动启动 → 窗口可见（state=normal）")

    # ---------- 3) 带 --silent（开机自启）时才隐藏窗口 ----------
    root2 = tk.Tk()
    app2 = make_app(root2, silent=True)
    app2._startup_report()
    root2.update()
    assert root2.state() == "withdrawn", f"静默启动应隐藏窗口，实际 {root2.state()}"
    print("[i] 开机自启（--silent）→ 后台驻留（state=withdrawn）")

    # ---------- 4) 静默驻留时再次双击 → 窗口应被叫出来 ----------
    assert signal_show_window(WORK) is True, "应能写出显示信号"
    assert (WORK / SHOW_SIGNAL_NAME).exists(), "信号文件应存在"
    app2._check_show_signal()
    # 窗口映射由 Tk 事件循环完成，多转几圈再判定
    for _ in range(5):
        root2.update()
    if root2.state() != "normal":
        print(f"[诊断] state={root2.state()} 信号文件存在={((WORK / SHOW_SIGNAL_NAME).exists())} "
              f"_closed={app2._closed} silent_start={app2.silent_start} 存储目录={app2.store.dir}")
    assert root2.state() == "normal", f"收到信号后应显示窗口，实际 {root2.state()}"
    assert not (WORK / SHOW_SIGNAL_NAME).exists(), "信号文件应被消费掉"
    assert consume_show_signal(WORK) is False, "消费后不应再有信号"
    print("[i] 后台驻留 + 再次双击 → 窗口被显示出来")

    # ---------- 5) 窗口已显示时不重复响应 ----------
    assert signal_show_window(WORK) is True
    app2._check_show_signal()          # 已 normal，应直接跳过、不动信号
    root2.update()
    assert (WORK / SHOW_SIGNAL_NAME).exists(), "窗口已显示时不应消费信号"
    (WORK / SHOW_SIGNAL_NAME).unlink()
    app2.quit_app()

    # ---------- 6) --silent --show 时仍然显示窗口 ----------
    root3 = tk.Tk()
    app3 = make_app(root3, silent=False)      # main() 里是 args.silent and not args.show
    root3.deiconify()
    root3.update()
    assert root3.state() == "normal"
    app3.quit_app()
    print("[i] --silent --show → 仍显示窗口")

    # ---------- 7) 用真实命令行入口验证单实例：第二个进程必须秒退 ----------
    import subprocess
    import time
    store = TaskStore(WORK)
    store.load()
    settings = build_settings()               # autostart=True，复现用户现场
    first = subprocess.Popen(
        [sys.executable, str(BASE / "main.py"), "--data", str(WORK)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(8)
    try:
        assert first.poll() is None, "第一个实例应持续运行"
        started = time.time()
        second = subprocess.run(
            [sys.executable, str(BASE / "main.py"), "--data", str(WORK)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45,
        )
        elapsed = time.time() - started
        assert second.returncode == 0, f"重复启动应正常退出，实际 {second.returncode}"
        assert elapsed < 30, f"重复启动应立刻退出，实际耗时 {elapsed:.1f} 秒"
        assert first.poll() is None, "原有实例不应被影响"
        print(f"[i] 重复启动 → 第二个进程 {elapsed:.1f} 秒后退出，原实例继续运行")
    finally:
        first.terminate()
        try:
            first.wait(timeout=10)
        except Exception:
            first.kill()

    print("[OK] 启动方式测试通过：手动启动可见 / 自启静默 / 再次双击唤起窗口 / 不重复开实例")
    return 0


if __name__ == "__main__":
    sys.exit(main())
