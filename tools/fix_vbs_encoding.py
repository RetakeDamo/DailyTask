# -*- coding: utf-8 -*-
"""把 .vbs 启动器转成 UTF-16LE(带 BOM)，避免 Windows 脚本宿主按 ANSI 读取中文时出错。

用法： python tools/fix_vbs_encoding.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TARGETS = ["启动任务提醒.vbs", "后台静默启动.vbs"]


def convert(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "已是 UTF-16"
    text = data.decode("utf-8-sig")
    path.write_bytes(b"\xff\xfe" + text.replace("\n", "\r\n").encode("utf-16-le"))
    return f"已转换为 UTF-16LE（{len(text)} 字符）"


def main() -> int:
    ok = True
    for name in TARGETS:
        path = BASE / name
        if not path.exists():
            print(f"  [跳过] 未找到 {name}")
            ok = False
            continue
        print(f"  [处理] {name} -> {convert(path)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
