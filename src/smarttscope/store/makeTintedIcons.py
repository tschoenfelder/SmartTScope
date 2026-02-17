import sys, os
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

def tinted_svg_icon(svg_path: str, color: QColor, size: QSize) -> QIcon:
    renderer = QSvgRenderer(svg_path)
    pm = QPixmap(size)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    renderer.render(p)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pm.rect(), color)
    p.end()

    return QIcon(pm)

def apply_red_green_icon(tb, svg_path: str,
                         red="#d32f2f", green="#2e7d32"):
    size = tb.iconSize()
    icon_red = tinted_svg_icon(svg_path, QColor(red), size)
    icon_green = tinted_svg_icon(svg_path, QColor(green), size)

    def update():
        tb.setIcon(icon_green if tb.isChecked() else icon_red)

    tb.toggled.connect(lambda _checked: update())
    update()  # initial


if __name__ == '__main__':
    iconsPath = Path(r"C:\Users\U070420\OneDrive - Lufthansa Group\Local Documents\SmartTScope\icons")
    print(dir(iconsPath))
    for iconPath in iconsPath.glob('**/*.svg'):
        # iconsPath.iterdir():
        print(iconPath)
        apply_red_green_icon(iconPath)
