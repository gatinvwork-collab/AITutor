"""Package the SVG brand resource as a standard multi-resolution Windows ICO."""
import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main():
    root = Path(__file__).resolve().parent.parent
    renderer = QSvgRenderer(str(root / "ui/assets/tutor-ai-mark.svg"))
    assert renderer.isValid()
    sizes = (16, 24, 32, 48, 64, 128, 256)
    entries, images = [], []
    offset = 6 + len(sizes) * 16
    for size in sizes:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer, "PNG")
        raw = bytes(data)
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(raw), offset))
        images.append(raw)
        offset += len(raw)
    icon = struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries + images)
    (root / "ui/assets/Tutor-AI.ico").write_bytes(icon)
    print("Packaged Windows icon sizes:", sizes)


if __name__ == "__main__":
    main()
