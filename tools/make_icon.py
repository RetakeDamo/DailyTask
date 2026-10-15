# -*- coding: utf-8 -*-
"""生成应用图标 app.ico（纯标准库，多尺寸：16/24/32/48/64/128/256）。

用法： python tools/make_icon.py [输出路径]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ACCENT = (47, 111, 235)      # 主色 #2f6feb
ACCENT_DARK = (24, 78, 180)
WHITE = (255, 255, 255)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def _rounded(x: float, y: float) -> bool:
    return True


def draw(size: int):
    """返回逐行 BGRA 像素（无压缩 32 位 BMP，自下而上）。"""
    px = [[(0, 0, 0, 0)] * size for _ in range(size)]
    r = size / 2.0
    margin = size * 0.04
    radius = size * 0.22
    cx = cy = (size - 1) / 2.0

    for y in range(size):
        for x in range(size):
            fx, fy = x + 0.5, y + 0.5
            # 圆角矩形背景
            dx = max(margin + radius - fx, fx - (size - margin - radius), 0.0)
            dy = max(margin + radius - fy, fy - (size - margin - radius), 0.0)
            if (dx * dx + dy * dy) ** 0.5 > radius and (dx > 0 or dy > 0):
                continue
            if fx < margin or fx > size - margin or fy < margin or fy > size - margin:
                continue
            # 渐变底色
            t = fy / size
            color = tuple(int(ACCENT[i] + (ACCENT_DARK[i] - ACCENT[i]) * t) for i in range(3))

            # 白色对勾
            if in_check(fx, fy, size):
                color = WHITE
            px[y][x] = (color[2], color[1], color[0], 255)   # BGRA
    return px


def in_check(fx: float, fy: float, size: int) -> bool:
    """判断点是否落在对勾笔画内。"""
    w = max(1.6, size * 0.105)      # 笔画粗细
    # 第一段：从左中到下部拐点
    p0 = (size * 0.24, size * 0.52)
    p1 = (size * 0.43, size * 0.71)
    # 第二段：从拐点到右上
    p2 = (size * 0.77, size * 0.30)
    return seg_dist(fx, fy, *p0, *p1) <= w / 2 or seg_dist(fx, fy, *p1, *p2) <= w / 2


def seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    vx, vy = x2 - x1, y2 - y1
    wx, wy = px - x1, py - y1
    denom = vx * vx + vy * vy
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
    dx, dy = x1 + t * vx - px, y1 + t * vy - py
    return (dx * dx + dy * dy) ** 0.5


def bmp_bytes(size: int) -> bytes:
    px = draw(size)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    body = bytearray()
    for y in range(size - 1, -1, -1):          # BMP 自下而上
        for x in range(size):
            b, g, r, a = px[y][x]
            body += bytes((b, g, r, a))
    # AND 掩码（32 位图可全 0，这里按透明度生成）
    row_bytes = ((size + 31) // 32) * 4
    mask = bytearray()
    for y in range(size - 1, -1, -1):
        bits = bytearray(row_bytes)
        for x in range(size):
            if px[y][x][3] < 128:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bits
    return header + bytes(body) + bytes(mask)


def build_ico(path: Path) -> Path:
    images = [(size, bmp_bytes(size)) for size in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, data in images:
        out += struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0,
                           0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _size, data in images:
        out += data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "app.ico"
    print("已生成图标:", build_ico(target), target.stat().st_size, "字节")
