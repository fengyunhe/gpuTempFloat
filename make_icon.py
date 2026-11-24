"""生成打包用的 app.ico（多尺寸：16~256），样式与托盘图标一致：深色圆角方块 + 绿色 G。"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

SIZES = (16, 24, 32, 48, 64, 128, 256)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "assets")
OUT_ICO = os.path.join(OUT_DIR, "app.ico")


def render(size: int) -> bytes:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    pad = max(1.0, size * 0.04)
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.22, size * 0.22)

    p.fillPath(path, QColor(14, 15, 18))
    p.setPen(QPen(QColor(61, 220, 132, 220), max(1.0, size / 32.0)))
    p.drawPath(path)

    f = QFont("Segoe UI", int(size * 0.62))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(61, 220, 132))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "G")
    p.end()

    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def build_ico() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    blobs = [(s, render(s)) for s in SIZES]

    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    body = b""
    for s, data in blobs:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        body += data
        offset += len(data)

    with open(OUT_ICO, "wb") as fh:
        fh.write(header + entries + body)
    print("icon written:", OUT_ICO, os.path.getsize(OUT_ICO), "bytes")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    build_ico()
