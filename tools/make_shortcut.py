# -*- coding: utf-8 -*-
"""在桌面 / 启动文件夹创建快捷方式。

用法：
    python tools/make_shortcut.py             只创建桌面快捷方式
    python tools/make_shortcut.py --startup   同时放入“启动”文件夹（开机自动驻留）
"""
from __future__ import annotations

import os
import subprocess
import sys
import winreg
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LAUNCHER = BASE / "启动任务提醒.vbs"
SILENT = BASE / "后台静默启动.vbs"
ICON = BASE / "app.ico"

_CREATE_LNK = r"""
$ErrorActionPreference = 'Stop'
$cfg = Get-Content -Raw -Encoding UTF8 -LiteralPath $args[0] | ConvertFrom-Json
$dir = Split-Path -Parent $cfg.path
if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($cfg.path)
$lnk.TargetPath = $cfg.target
$lnk.Arguments = $cfg.args
$lnk.WorkingDirectory = $cfg.cwd
if ($cfg.icon -and (Test-Path -LiteralPath $cfg.icon)) { $lnk.IconLocation = "$($cfg.icon),0" }
else { $lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,23" }
$lnk.Description = [string]$cfg.desc
$lnk.Save()
Write-Output 'LNK-OK'
"""


def _hidden_flags() -> int:
    return 0x08000000 if sys.platform == "win32" else 0


def desktop_dir() -> Path:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            value, _ = winreg.QueryValueEx(key, "Desktop")
        return Path(os.path.expandvars(value))
    except Exception:
        return Path(os.path.expanduser("~")) / "Desktop"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def find_wscript() -> str:
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(system_root) / "System32" / "wscript.exe"
    return str(candidate) if candidate.exists() else "wscript.exe"


def create_shortcut(lnk_path: Path, target: str, args: str = "", cwd: Path = BASE,
                    desc: str = "每日任务提醒 —— 每日循环任务与一次性任务提醒") -> bool:
    import json
    build = BASE / ".build"
    build.mkdir(parents=True, exist_ok=True)
    ps1 = build / "dtr_make_shortcut.ps1"
    cfg = build / "dtr_shortcut.json"
    ps1.write_text(_CREATE_LNK, encoding="utf-8-sig")
    cfg.write_text(json.dumps({
        "path": str(lnk_path),
        "target": target,
        "args": args,
        "cwd": str(cwd),
        "icon": str(ICON),
        "desc": desc,
    }, ensure_ascii=False), encoding="utf-8")

    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", str(ps1), str(cfg)],
            capture_output=True, timeout=40, creationflags=_hidden_flags(),
        )
        ok = proc.returncode == 0 and b"LNK-OK" in (proc.stdout or b"")
        if not ok:
            print("  PowerShell 输出:", (proc.stdout or b"").decode("utf-8", "ignore").strip(),
                  (proc.stderr or b"").decode("utf-8", "ignore").strip())
        return ok
    except Exception as exc:
        print("  创建失败:", exc)
        return False


def main() -> int:
    with_startup = "--startup" in sys.argv or "-s" in sys.argv
    launcher = LAUNCHER if LAUNCHER.exists() else None
    silent = SILENT if SILENT.exists() else launcher

    if launcher and launcher.suffix.lower() == ".vbs":
        target, args = find_wscript(), f'"{launcher}"'
        silent_args = f'"{silent}"' if silent else f'"{launcher}"'
    else:
        target, args, silent_args = sys.executable, str(BASE / "main.py"), str(BASE / "main.py")

    results = []
    results.append(("桌面", create_shortcut(desktop_dir() / "每日任务提醒.lnk", target, args)))
    if with_startup:
        results.append(("启动文件夹（代理到本程序的自启开关）",
                        create_shortcut(startup_dir() / "每日任务提醒.lnk", target, silent_args)))

    for name, ok in results:
        print(("  [成功] " if ok else "  [失败] ") + name)
    print("\n提示：也可以在程序界面里点「系统 → 开机自动启动」来设置自启，二者选其一即可。")
    return 0 if all(ok for _n, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
