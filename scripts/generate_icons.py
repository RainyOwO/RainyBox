#!/usr/bin/env python3
"""生成 RainyBox 图标（红/绿/蓝渐变）。"""

from __future__ import annotations

import struct
import subprocess
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
ICONSET_DIR = ASSETS_DIR / "icon.iconset"


def gradient_color(t: float) -> tuple[int, int, int]:
    """红 → 绿 → 蓝 的渐变色。"""
    if t <= 0.5:
        k = t / 0.5
        r = int(255 * (1 - k))
        g = int(255 * k)
        b = 0
        return r, g, b
    k = (t - 0.5) / 0.5
    r = 0
    g = int(255 * (1 - k))
    b = int(255 * k)
    return r, g, b


def write_png(path: Path, size: int) -> None:
    """用标准库写出 PNG（RGB、无透明通道）。"""
    width = height = size
    rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        ny = y / (height - 1)
        for x in range(width):
            nx = x / (width - 1)
            t = (nx + ny) / 2.0
            r, g, b = gradient_color(t)
            # 轻微高光：让图标更有质感
            highlight = max(0.0, 0.4 - (nx * nx + ny * ny) ** 0.5)
            if highlight > 0:
                r = min(255, int(r + 255 * highlight))
                g = min(255, int(g + 255 * highlight))
                b = min(255, int(b + 255 * highlight))
            row.extend([r, g, b])
        rows.append(bytes(row))

    raw = b"".join(b"\x00" + row for row in rows)
    compressed = zlib.compress(raw, level=9)

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack("!I", len(data))
        crc = struct.pack("!I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return length + chunk_type + data + crc

    ihdr = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
    path.write_bytes(png)


def build_ico(png_map: dict[int, bytes], output: Path) -> None:
    """生成 ICO 文件（用 PNG 作为图像数据）。"""
    sizes = sorted(png_map.keys())
    header = struct.pack("!HHH", 0, 1, len(sizes))
    entries = []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        data = png_map[size]
        width = size if size < 256 else 0
        height = size if size < 256 else 0
        entry = struct.pack(
            "!BBBBHHII",
            width,
            height,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        entries.append(entry)
        offset += len(data)
    output.write_bytes(header + b"".join(entries) + b"".join(png_map[size] for size in sizes))


def main() -> None:
    """生成 PNG、ICO、ICNS。"""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    ICONSET_DIR.mkdir(parents=True, exist_ok=True)

    # 1) 基础 PNG（1024）
    base_png = ASSETS_DIR / "icon.png"
    write_png(base_png, 1024)

    # 2) ICO（多尺寸）
    ico_sizes = [16, 32, 48, 64, 128, 256]
    ico_map: dict[int, bytes] = {}
    for size in ico_sizes:
        temp = ASSETS_DIR / f"icon_{size}.png"
        write_png(temp, size)
        ico_map[size] = temp.read_bytes()
        temp.unlink(missing_ok=True)
    build_ico(ico_map, ASSETS_DIR / "icon.ico")

    # 3) ICNS（iconset + iconutil）
    iconset_specs = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }
    for filename, size in iconset_specs.items():
        write_png(ICONSET_DIR / filename, size)

    subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET_DIR), "-o", str(ASSETS_DIR / "icon.icns")],
        check=True,
    )


if __name__ == "__main__":
    main()
