# -*- coding: utf-8 -*-
"""每日任务提醒 —— 程序入口。

用法：
    pythonw main.py                正常启动
    pythonw main.py --silent       启动后直接驻留后台（开机自启用）
    pythonw main.py --data DIR     指定数据目录（默认 %APPDATA%\\DailyTaskReminder）
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import tkinter as tk
from pathlib import Path

# 允许直接以脚本方式运行
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_task import __version__
from daily_task.history import HistoryStore
from daily_task.settings import Settings, set_autostart
from daily_task.tasks import TaskStore
from daily_task.ui import APP_TITLE, TaskApp

MUTEX_NAME = "Local\\DailyTaskReminder_SingleInstance_v3"
LOCK_FILE_NAME = "instance.lock"
ERROR_FILE_NOT_FOUND = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000


def _mutex_exists() -> bool:
    """用 OpenMutexW 判断同名互斥体是否已存在。

    比 CreateMutexW + GetLastError 可靠：不依赖线程错误码是否被覆盖，
    跨用户/沙箱上下文也能正确判定「有实例在跑」。
    """
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenMutexW.restype = ctypes.c_void_p
        kernel32.OpenMutexW.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenMutexW(SYNCHRONIZE, 0, MUTEX_NAME)
        if handle:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            return True
        return False
    except Exception:
        return False


def _process_alive_and_ours(pid: int) -> bool:
    """确认 pid 是否真的是一个还在运行的本程序进程，避免残留对象误判。"""
    if not pid or sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
        kernel32.QueryFullProcessImageNameW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint),
        ]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, 0, int(pid))
        if not handle:
            return False                     # 进程已经不存在
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_uint(1024)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return True                  # 查不到名字但进程在，保守认为还活着
            return Path(buffer.value).name.lower() in (
                "python.exe", "pythonw.exe", "dailytaskreminder.exe",
            )
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    except Exception:
        return False


def _lock_owner_path(data_dir=None) -> Path:
    from daily_task.tasks import default_data_dir
    target = Path(data_dir) if data_dir else default_data_dir()
    return target / LOCK_FILE_NAME


def _read_lock_owner(data_dir=None) -> int:
    try:
        path = _lock_owner_path(data_dir)
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            return int(text) if text.isdigit() else 0
    except Exception:
        pass
    return 0


def _write_lock_owner(data_dir=None) -> None:
    try:
        path = _lock_owner_path(data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def _acquire_mutex() -> bool:
    """持有本进程的互斥体。"""
    if sys.platform != "win32":
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateMutexW(None, 0, MUTEX_NAME)
        if not handle:
            return True                   # 创建失败不要拦住用户
        acquire_single_instance._handle = handle
        acquire_single_instance._kernel32 = kernel32
        return True
    except Exception:
        return True


def acquire_single_instance(data_dir=None) -> bool:
    """判定本进程能否启动：True = 唯一实例。

    判定依据：
      1. instance.lock 里记录的 pid 是否还是一个活着的本程序进程（最可靠）；
      2. 同名命名互斥体是否存在。

    两者都是「有实例在跑」的信号；但如果互斥体还在、而记录里的进程已经不存在，
    就当成残留对象（上次被强杀、或受限环境回收了进程却留下内核对象），
    照常启动 —— 宁可偶尔多开一个，也不能让用户点了打不开。
    """
    owner_pid = _read_lock_owner(data_dir)
    if owner_pid == os.getpid() and getattr(acquire_single_instance, "_handle", None):
        return False                     # 本进程已经持有单实例标记
    owner_alive = _process_alive_and_ours(owner_pid)
    if owner_alive and owner_pid != os.getpid():
        return False
    if _mutex_exists() and owner_alive:
        return False
    _acquire_mutex()
    _write_lock_owner(data_dir)
    return True


def _release_mutex() -> None:
    handle = getattr(acquire_single_instance, "_handle", None)
    kernel32 = getattr(acquire_single_instance, "_kernel32", None)
    if handle and kernel32 is not None:
        try:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        except Exception:
            pass
    acquire_single_instance._handle = None


def release_single_instance(data_dir=None) -> None:
    """释放单实例标记（正常退出时由系统回收，测试里手动清理）。"""
    _release_mutex()
    try:
        path = _lock_owner_path(data_dir)
        if path.exists() and _read_lock_owner(data_dir) == os.getpid():
            path.unlink()
    except Exception:
        pass


def already_running_notice(data_dir=None) -> None:
    """已有一个实例在跑：请它把窗口显示出来，然后本进程立刻退出。

    注意：这里刻意**不**发系统通知 —— 已经运行的实例收到信号后会自己弹到前面，
    而在这个路径里起外部进程（PowerShell）既慢又可能被安全软件拦住。
    """
    try:
        from daily_task.settings import signal_show_window
        signal_show_window(data_dir)       # 正在运行的实例会把窗口弹出来
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="每日任务提醒")
    parser.add_argument("--silent", action="store_true", help="启动后最小化到后台")
    parser.add_argument("--show", action="store_true", help="强制显示主窗口")
    parser.add_argument("--data", default="", help="数据目录")
    parser.add_argument("--version", action="store_true", help="显示版本")
    args = parser.parse_args(argv)

    if args.version:
        print(f"{APP_TITLE} v{__version__}")
        return 0

    data_dir = Path(args.data) if args.data else None

    if not acquire_single_instance(data_dir):
        # 已经有实例在运行：请它把窗口显示出来，然后本进程退出
        already_running_notice(data_dir)
        return 0

    store = TaskStore(data_dir)
    store.load()
    history = HistoryStore(data_dir)
    history.load()
    settings = Settings.load(data_dir)

    # 已经开启自启的话，把注册表里的命令刷新成当前程序位置（开机静默驻留）
    if settings.autostart:
        set_autostart(True)

    root = tk.Tk()
    app = TaskApp(root, store, settings, silent_start=args.silent and not args.show, history=history)
    try:
        root.mainloop()
    finally:
        try:
            store.save()
            settings.save(data_dir)
            history.save()
        except Exception:
            pass
        release_single_instance(data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
