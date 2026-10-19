"""Gera os ícones PNG da PWA sem dependências externas."""

from pathlib import Path
import struct
import zlib


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "pwa"
BACKGROUND = (16, 39, 71, 255)
ACCENT = (65, 215, 176, 255)


def rounded_bar(pixels, size, left, top, right, bottom, radius, color):
    for y in range(top, bottom):
        for x in range(left, right):
            nearest_x = min(max(x, left + radius), right - radius - 1)
            nearest_y = min(max(y, top + radius), bottom - radius - 1)
            if (x - nearest_x) ** 2 + (y - nearest_y) ** 2 <= radius ** 2:
                offset = (y * size + x) * 4
                pixels[offset : offset + 4] = bytes(color)


def write_png(size):
    pixels = bytearray(BACKGROUND * (size * size))
    bar_width = round(size * 0.115)
    radius = bar_width // 2
    baseline = round(size * 0.75)
    for center, height in (
        (round(size * 0.30), round(size * 0.29)),
        (round(size * 0.50), round(size * 0.45)),
        (round(size * 0.70), round(size * 0.61)),
    ):
        rounded_bar(
            pixels,
            size,
            center - bar_width // 2,
            baseline - height,
            center + bar_width // 2,
            baseline,
            radius,
            ACCENT,
        )

    scanlines = b"".join(
        b"\x00" + pixels[row * size * 4 : (row + 1) * size * 4]
        for row in range(size)
    )

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(scanlines, 9))
    png += chunk(b"IEND", b"")
    (OUTPUT_DIR / f"icon-{size}.png").write_bytes(png)


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for icon_size in (180, 192, 512):
        write_png(icon_size)
