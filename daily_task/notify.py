# -*- coding: utf-8 -*-
"""提醒方式：
1) Windows 系统通知（气泡 / 操作中心）
2) 自绘的右下角弹窗（始终可用，可点“稍后提醒”）
3) 声音提示
"""
from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from typing import Callable, List, Optional

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_PS_CANDIDATES = ["powershell.exe", "pwsh.exe"]
# 方案 A：气泡通知（Win32 Shell_NotifyIcon，兼容性最好）
_BALLOON_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$ni = New-Object System.Windows.Forms.NotifyIcon
$ni.Icon = [System.Drawing.SystemIcons]::Information
$ni.Visible = $true
$ni.BalloonTipTitle = $env:DSH_NI_TITLE
$ni.BalloonTipText = $env:DSH_NI_TEXT
$ni.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
$ni.ShowBalloonTip(8000)
Start-Sleep -Milliseconds 3200
$ni.Visible = $false
$ni.Dispose()
"""

# 方案 B：WinRT 系统通知（需要通知程序标识，部分环境不可用）
_TOAST_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:DSH_TOAST_XML)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:DSH_TOAST_APPID).Show($toast)
"""

_DETACHED_PROCESS = 0x00000008 if sys.platform == "win32" else 0
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def play_sound(style: str = "default") -> None:
    """异步播放提示音，失败静默。"""
    def worker() -> None:
        if sys.platform != "win32":
            return
        try:
            import winsound
            if style == "alarm":
                for freq in (880, 1046, 880, 1046):
                    winsound.Beep(freq, 160)
            else:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def _run_powershell(script: str, extra_env: dict) -> bool:
    """后台静默执行一段 PowerShell；不阻塞主流程，失败就当没发通知。"""
    import os
    env = dict(os.environ)
    env.update(extra_env)
    for exe in _PS_CANDIDATES:
        try:
            proc = subprocess.Popen(
                [exe, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW | _DETACHED_PROCESS,
                close_fds=True,
            )
        except FileNotFoundError:
            continue
        except Exception:
            continue
        # 只等一会儿，绝不因为外部进程拖住提醒流程
        try:
            return proc.wait(timeout=8) == 0
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            return True          # 已经发出去了，只是没等到退出码
    return False


def show_windows_toast(title: str, message: str, app_id: str = "DailyTaskReminder") -> bool:
    """弹一条系统级通知（右下角气泡 / 通知中心）；返回是否成功。"""
    if sys.platform != "win32":
        return False
    text = str(message).replace("\n", "  ")
    if _run_powershell(_BALLOON_SCRIPT, {"DSH_NI_TITLE": str(title)[:60], "DSH_NI_TEXT": text[:250]}):
        return True
    xml = (
        "<toast duration='long'>"
        "<visual><binding template='ToastGeneric'>"
        f"<text>{_xml_escape(title)}</text>"
        f"<text>{_xml_escape(text)}</text>"
        "</binding></visual>"
        "<audio src='ms-winsoundevent:Notification.Reminder'/>"
        "</toast>"
    )
    return _run_powershell(_TOAST_SCRIPT, {"DSH_TOAST_XML": xml, "DSH_TOAST_APPID": app_id})


# --------------------------------------------------------------------------- #
# 自绘弹窗
# --------------------------------------------------------------------------- #
class ToastPopup:
    """右下角提醒卡片，支持「稍后提醒 / 完成」回调。"""

    WIDTH = 360
    MARGIN = 18
    STACK_GAP = 10

    _stack: List["ToastPopup"] = []

    def __init__(self, master: tk.Misc, title: str, body: str, accent: str = "#2f6feb",
                 on_snooze: Optional[Callable[[], None]] = None,
                 on_done: Optional[Callable[[], None]] = None,
                 on_open: Optional[Callable[[], None]] = None,
                 auto_close_ms: int = 20000):
        self.closed = False
        self.on_snooze = on_snooze
        self.on_done = on_done
        self.on_open = on_open

        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.0)
        except Exception:
            pass
        self.win.configure(bg="#d8dde5")

        shell = tk.Frame(self.win, bg="#ffffff", highlightthickness=0)
        shell.pack(fill="both", expand=True, padx=1, pady=1)

        stripe = tk.Frame(shell, bg=accent, height=4)
        stripe.pack(fill="x")

        pad = tk.Frame(shell, bg="#ffffff")
        pad.pack(fill="both", expand=True, padx=16, pady=(12, 10))

        head = tk.Frame(pad, bg="#ffffff")
        head.pack(fill="x")
        tk.Label(head, text="⏰  任务提醒", bg="#ffffff", fg="#8a94a6",
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        tk.Label(head, text=datetime.now().strftime("%H:%M"), bg="#ffffff", fg="#b3bbc9",
                 font=("Consolas", 9)).pack(side="right")

        tk.Label(pad, text=title, bg="#ffffff", fg="#1b2430", justify="left",
                 wraplength=self.WIDTH - 60, anchor="w",
                 font=("Microsoft YaHei UI", 12, "bold")).pack(fill="x", pady=(8, 0))
        if body:
            tk.Label(pad, text=body, bg="#ffffff", fg="#5d6b7e", justify="left",
                     wraplength=self.WIDTH - 60, anchor="w",
                     font=("Microsoft YaHei UI", 9)).pack(fill="x", pady=(4, 0))

        buttons = tk.Frame(pad, bg="#ffffff")
        buttons.pack(fill="x", pady=(12, 0))
        if on_snooze:
            self._button(buttons, "稍后 5 分钟", "#f3f5f9", "#33415c", self._snooze).pack(side="left")
        if on_done:
            self._button(buttons, "标记完成", "#e8f1ff", "#1d4ed8", self._done).pack(side="left", padx=(6, 0))
        self._button(buttons, "知道了", accent, "#ffffff", self.close).pack(side="right")

        self.win.update_idletasks()
        self.height = self.win.winfo_reqheight()
        self._place()
        ToastPopup._stack.append(self)

        try:
            self.win.deiconify()
        except Exception:
            pass
        self._fade_in()
        if auto_close_ms:
            self.win.after(auto_close_ms, self.close)

    # -------------------- 内部 -------------------- #
    def _button(self, parent: tk.Misc, text: str, bg: str, fg: str, command: Callable[[], None]) -> tk.Label:
        lbl = tk.Label(parent, text=text, bg=bg, fg=fg, padx=12, pady=5,
                       cursor="hand2", font=("Microsoft YaHei UI", 9))
        lbl.bind("<Button-1>", lambda _e: command())
        lbl.bind("<Enter>", lambda _e: lbl.configure(bg=self._hover(bg)))
        lbl.bind("<Leave>", lambda _e: lbl.configure(bg=bg))
        return lbl

    @staticmethod
    def _hover(bg: str) -> str:
        table = {"#f3f5f9": "#e6ebf3", "#e8f1ff": "#d7e6ff", "#2f6feb": "#2559c9", "#e5484d": "#c93a3f"}
        return table.get(bg, bg)

    def _place(self) -> None:
        try:
            screen_w = self.win.winfo_screenwidth()
            screen_h = self.win.winfo_screenheight()
        except Exception:
            screen_w, screen_h = 1920, 1080
        offset = 0
        for popup in ToastPopup._stack:
            if popup is self or popup.closed:
                continue
            offset += popup.height + self.STACK_GAP
        x = screen_w - self.WIDTH - self.MARGIN
        y = screen_h - self.height - self.MARGIN - offset - 60
        self.win.geometry(f"{self.WIDTH}x{self.height}+{max(0, x)}+{max(40, y)}")

    def _fade_in(self, alpha: float = 0.0) -> None:
        if self.closed:
            return
        alpha = min(1.0, alpha + 0.18)
        try:
            self.win.attributes("-alpha", alpha)
        except Exception:
            return
        if alpha < 1.0:
            self.win.after(18, lambda: self._fade_in(alpha))

    def _forget(self) -> None:
        try:
            ToastPopup._stack.remove(self)
        except ValueError:
            pass

    def _snooze(self) -> None:
        callback = self.on_snooze
        self.close()
        if callback:
            callback()

    def _done(self) -> None:
        callback = self.on_done
        self.close()
        if callback:
            callback()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._forget()
        try:
            self.win.destroy()
        except Exception:
            pass
        for popup in ToastPopup._stack:
            popup._place()
