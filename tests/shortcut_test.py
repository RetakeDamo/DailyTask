# -*- coding: utf-8 -*-
"""在 .build/shots 下测试快捷方式创建（不写入真实桌面）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.make_shortcut import BASE, create_shortcut, find_wscript  # noqa: E402


def main() -> int:
    out = BASE / ".build" / "shots" / "每日任务提醒.lnk"
    if out.exists():
        out.unlink()
    args = '"' + str(BASE / "启动任务提醒.vbs") + '"'
    ok = create_shortcut(out, find_wscript(), args, BASE, "快捷方式测试")
    print("  wscript:", find_wscript())
    print("  创建结果:", ok, "| 文件存在:", out.exists(),
          "|", out.stat().st_size if out.exists() else 0, "字节")
    if out.exists():
        content = out.read_bytes()
        print("  含图标路径:", str(BASE / "app.ico").encode("utf-16-le") in content or str(BASE / "app.ico").encode("gbk") in content)
        print("  含中文名:", "每日任务提醒".encode("utf-16-le") in content)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
