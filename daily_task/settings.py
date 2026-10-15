# -*- coding: utf-8 -*-
"""应用设置与 Windows 开机自启。"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .tasks import default_data_dir

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "DailyTaskReminder"

# 第二次启动时留下的信号文件：正在后台运行的实例看到后会把自己显示出来
SHOW_SIGNAL_NAME = "show.request"


@dataclass
class Settings:
    autostart: bool = False
    windows_toast: bool = True     # 弹窗提醒之外，同时发一条系统通知
    sound: bool = True
    show_finished: bool = True
    one_time_auto_done: bool = False  # 一次性任务提醒后自动标记完成
    dark_mode: bool = False           # 深色模式
    data_dir: Optional[Path] = field(default=None, repr=False, compare=False)  # 自定义数据目录

    # -------------------- 读写 -------------------- #
    @staticmethod
    def path(data_dir: Optional[Path] = None) -> Path:
        return (Path(data_dir) if data_dir else default_data_dir()) / "settings.json"

    @classmethod
    def load(cls, data_dir: Optional[Path] = None) -> "Settings":
        target = Path(data_dir) if data_dir else None
        p = cls.path(target)
        if not p.exists():
            return cls(data_dir=target)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            data: Dict[str, Any] = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            data.pop("data_dir", None)
            obj = cls(**data)
        except Exception:
            obj = cls()
        obj.data_dir = target
        return obj

    def save(self, data_dir: Optional[Path] = None) -> bool:
        """保存设置；失败返回 False（不抛出，避免影响正常使用）。"""
        p = self.path(data_dir or self.data_dir)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str),
                         encoding="utf-8")
            return True
        except Exception:
            return False


# --------------------------------------------------------------------------- #
# 开机自启
# --------------------------------------------------------------------------- #
def pythonw_path() -> str:
    """优先使用 pythonw.exe，避免弹出黑窗口。"""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        return str(exe)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def launch_command(silent: bool = False) -> str:
    """启动命令；silent=True 时（开机自启）只在后台驻留，不弹主窗口。"""
    if getattr(sys, "frozen", False):
        base = f'"{Path(sys.executable)}"'
    else:
        main_py = Path(__file__).resolve().parent.parent / "main.py"
        base = f'"{pythonw_path()}" "{main_py}"'
    if silent:
        return base + " --silent"
    return base


def autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return bool(value)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_autostart(enabled: bool) -> tuple[bool, str]:
    """写入/删除注册表自启项，返回 (是否成功, 说明)。

    写入的命令带 --silent：开机时在后台驻留，不弹主窗口；
    用户手动双击启动器不受影响，始终显示窗口。
    """
    if sys.platform != "win32":
        return False, "仅支持 Windows"
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command(silent=True))
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True, launch_command() if enabled else ""
    except Exception as exc:
        return False, str(exc)


def signal_show_window(data_dir: Optional[Path] = None) -> bool:
    """请已经在运行的实例把主窗口显示出来（写一个信号文件）。"""
    try:
        target = (Path(data_dir) if data_dir else default_data_dir())
        target.mkdir(parents=True, exist_ok=True)
        (target / SHOW_SIGNAL_NAME).write_text(datetime.now().isoformat(), encoding="utf-8")
        return True
    except Exception:
        return False


def consume_show_signal(data_dir: Optional[Path] = None) -> bool:
    """检查并消费信号；返回 True 表示请求方希望显示窗口。"""
    try:
        target = (Path(data_dir) if data_dir else default_data_dir())
        signal = target / SHOW_SIGNAL_NAME
        if signal.exists():
            signal.unlink()
            return True
    except Exception:
        pass
    return False


def verify_launch_target() -> Optional[str]:
    """给界面用：检查开机自启指向的程序是否还存在。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
    except Exception:
        return None
    import shlex
    try:
        parts = shlex.split(str(value), posix=False)
    except Exception:
        return None
    target = parts[0].strip('"') if parts else ""
    if target and not os.path.exists(target):
        return f"自启指向的程序不存在：{target}"
    return None
