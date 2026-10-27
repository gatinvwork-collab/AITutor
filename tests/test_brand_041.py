"""Verify actual Windows ICO directory, local artwork and Qt icon loading."""
import struct
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent


def test_windows_ico_has_valid_png_frames_and_transparent_corners():
    raw = (ROOT / "ui/assets/Tutor-AI.ico").read_bytes()
    assert struct.unpack_from("<HHH", raw) == (0, 1, 7)
    sizes = []
    for index in range(7):
        width, height, _, _, planes, bits, length, offset = struct.unpack_from("<BBBBHHII", raw, 6 + index * 16)
        width, height = width or 256, height or 256
        image = QImage.fromData(raw[offset:offset + length], "PNG")
        assert planes == 1 and bits == 32 and not image.isNull()
        assert (image.width(), image.height()) == (width, height)
        assert image.pixelColor(0, 0).alpha() == 0
        assert image.pixelColor(width // 2, height // 2).alpha() > 0
        sizes.append(width)
    assert sizes == [16, 24, 32, 48, 64, 128, 256]


def test_brand_svg_is_standalone_and_readable_on_current_backgrounds():
    path = ROOT / "ui/assets/tutor-ai-mark.svg"
    text = path.read_text(encoding="utf-8")
    assert "http://" not in text.replace('http://www.w3.org/2000/svg', '').replace('http://www.w3.org/1999/xlink', '')
    renderer = QSvgRenderer(str(path))
    assert renderer.isValid()
    image = QImage(128, 128, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    assert image.pixelColor(0, 0).alpha() == 0
    # Raster antialiasing in the supplied/derived artwork may be near-opaque.
    assert image.pixelColor(64, 64).alpha() >= 240
