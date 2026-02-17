# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'SmartTScope.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################
import sys, os

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

def _render_svg_tinted(svg_path: str, color: QColor, size: QSize, dpr: float) -> QPixmap:
    w = max(1, int(size.width() * dpr))
    h = max(1, int(size.height() * dpr))

    pm = QPixmap(w, h)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    QSvgRenderer(svg_path).render(p)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pm.rect(), color)
    p.end()
    return pm

def make_two_state_icon(svg_path: str, size: QSize, dpr: float,
                        off="#d32f2f", on="#2e7d32") -> QIcon:
    pm_off = _render_svg_tinted(svg_path, QColor(off), size, dpr)
    pm_on  = _render_svg_tinted(svg_path, QColor(on),  size, dpr)

    ic = QIcon()
    for mode in (QIcon.Normal, QIcon.Active, QIcon.Selected, QIcon.Disabled):
        ic.addPixmap(pm_off, mode, QIcon.Off)
        ic.addPixmap(pm_on,  mode, QIcon.On)
    return ic
