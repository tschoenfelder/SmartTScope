# -*- coding: utf-8 -*-
import sys, os

# when adding icons, update resources.qrc and run pyside6-rcc resources.qrc -o src\smarttscope\ui\resources_rc.py
from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect, 
    QSize, QTime, QUrl, Qt, QTimer, QFile)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow, QMenuBar,
                               QSizePolicy, QStatusBar, QVBoxLayout, QWidget,
                               QHBoxLayout, QLabel, QSizePolicy,
                               QToolButton)
from PySide6.QtSvg import QSvgRenderer
import numpy as np

from .ui.ui_smarttscope import Ui_MainWindow
from .widgets.overlay_image_widget import OverlayImageWidget
from .icons import make_two_state_icon 
##from . import resources_rc

class RedGreenIcons:
    def __init__(self, svg_path: str, size: QSize):
        self.red = tinted_svg_icon(svg_path, QColor("#C11B17"), size) # "#d32f2f"
        self.green = tinted_svg_icon(svg_path, QColor("#2AAD0C"), size) # "#2e7d32"

def bind_action_red_green(action, svg_path, size, dpr):
    action.setCheckable(True)
    action.setEnabled(True)

    icon_red = make_two_state_icon(svg_path, size, dpr, off="#d32f2f", on="#d32f2f")
    icon_green = make_two_state_icon(svg_path, size, dpr, off="#2e7d32", on="#2e7d32")

    # Referenzen halten (sonst kann Python-GC in seltenen Fällen zuschlagen)
    action._icon_red = icon_red
    action._icon_green = icon_green

    def sync(checked: bool):
        action.setIcon(icon_green if checked else icon_red)

    action.toggled.connect(sync)
    sync(action.isChecked())

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

##class Ui_MainWindow(object):
##    def setupUi(self, MainWindow):
##        if not MainWindow.objectName():
##            MainWindow.setObjectName(u"MainWindow")
##        MainWindow.resize(1112, 889)
##        self.actionIndiConnected = QAction(MainWindow)
##        self.actionIndiConnected.setObjectName(u"actionIndiConnected")
##        self.actionIndiConnected.setCheckable(True)
##        icon = QIcon()
##        icon.addFile(u":/icons/block_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
##        self.actionIndiConnected.setIcon(icon)
##        self.actionMountUnparked = QAction(MainWindow)
##        self.actionMountUnparked.setObjectName(u"actionMountUnparked")
##        self.actionMountUnparked.setCheckable(True)
##        icon1 = QIcon()
##        icon1.addFile(u":/icons/sync_disabled_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
##        icon1.addFile(u":/icons/sync_disabled_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg", QSize(), QIcon.Mode.Normal, QIcon.State.On)
##        self.actionMountUnparked.setIcon(icon1)
##        self.actionTrackingOn = QAction(MainWindow)
##        self.actionTrackingOn.setObjectName(u"actionTrackingOn")
##        self.actionTrackingOn.setCheckable(True)
##        icon2 = QIcon()
##        icon2.addFile(u":/icons/target.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
##        self.actionTrackingOn.setIcon(icon2)
##
##        action = self.actionTrackingOn
##        action.setCheckable(True)
##        action.setEnabled(True)
##
##        size = QSize(18, 18)
##        screen = QApplication.primaryScreen()
##        dpr = screen.devicePixelRatio() if screen else 1.0
####        dpr = self.devicePixelRatioF()
##        action.setIcon(make_two_state_icon(":/icons/target.svg", size, dpr))
##
##        ic = make_two_state_icon(":/icons/target.svg", QSize(18,18),
##                                 self.devicePixelRatioF())
##        pm = ic.pixmap(18,18, QIcon.Normal, QIcon.On)
##        print(pm.toImage().pixelColor(9,9))   # sollte nicht grau sein
##
##
##        # Status setzen:
##        action.setChecked(True)   # grün
##        action.setChecked(False)  # rot
##
##        self.MainContainer = QWidget(MainWindow)
##        self.MainContainer.setObjectName(u"MainContainer")
##        self.verticalLayout = QVBoxLayout(self.MainContainer)
##        self.verticalLayout.setObjectName(u"verticalLayout")
##        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
##        self.horizontalLayout = QHBoxLayout()
##        self.horizontalLayout.setSpacing(4)
##        self.horizontalLayout.setObjectName(u"horizontalLayout")
##        self.camera1View = OverlayImageWidget(self.MainContainer)
##        self.camera1View.setObjectName(u"camera1View")
##        self.camera1View.setMinimumSize(QSize(320, 240))
##
##        self.horizontalLayout.addWidget(self.camera1View)
##
##        self.RightCams = QVBoxLayout()
##        self.RightCams.setObjectName(u"RightCams")
##        self.camera3View = OverlayImageWidget(self.MainContainer)
##        self.camera3View.setObjectName(u"camera3View")
##        self.camera3View.setMinimumSize(QSize(320, 240))
##
##        self.RightCams.addWidget(self.camera3View)
##
##        self.camera2View = OverlayImageWidget(self.MainContainer)
##        self.camera2View.setObjectName(u"camera2View")
##        self.camera2View.setMinimumSize(QSize(320, 240))
##
##        self.RightCams.addWidget(self.camera2View)
##
##        self.horizontalLayout.addLayout(self.RightCams)
##
##        self.horizontalLayout.setStretch(0, 2)
##        self.horizontalLayout.setStretch(1, 1)
##
##        self.verticalLayout.addLayout(self.horizontalLayout)
##
##        MainWindow.setCentralWidget(self.MainContainer)
##        self.menubar = QMenuBar(MainWindow)
##        self.menubar.setObjectName(u"menubar")
##        self.menubar.setGeometry(QRect(0, 0, 1112, 21))
##        MainWindow.setMenuBar(self.menubar)
##
##        self.statusbar = QStatusBar(MainWindow)
##        self.statusbar.setObjectName(u"statusbar")
##        MainWindow.setStatusBar(self.statusbar)
##
##        self.statusText = QLabel("Ready")
##        self.statusText.setTextFormat(Qt.PlainText)
##        self.statusText.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
##        self.statusText.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
##
##        # Stretch=1 => füllt links den Platz und “drückt” rechts die Permanent-Widgets an den Rand
##        self.statusbar.addWidget(self.statusText, 1)
##
##        self.statusLog = QLabel("")   # z.B. letzte Meldung
##        self.statusLog.setTextFormat(Qt.PlainText)
##        self.statusLog.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
##        self.statusLog.setMinimumWidth(260)
##
##        self.statusbar.addPermanentWidget(self.statusLog)  # rechts, vor den Icons
####        self.statusbar.addPermanentWidget(grp)             # deine ToolButtons-Gruppe ganz rechts
##
##        self.retranslateUi(MainWindow)
##
##        QMetaObject.connectSlotsByName(MainWindow)
##    # setupUi
##
##    def retranslateUi(self, MainWindow):
##        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
##        self.actionIndiConnected.setText(QCoreApplication.translate("MainWindow", u"actionIndiConnected", None))
##        self.actionMountUnparked.setText(QCoreApplication.translate("MainWindow", u"actionMountUnparked", None))
##        self.actionTrackingOn.setText(QCoreApplication.translate("MainWindow", u"actionTrackingOn", None))
##    # retranslateUi

def _mk_status_tb(action):
    tb = QToolButton()
    tb.setDefaultAction(action)
    tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
    tb.setAutoRaise(True)
    tb.setEnabled(True)
    tb.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Anzeige-only
    tb.setFocusPolicy(Qt.NoFocus)
    tb.setIconSize(QSize(18, 18))
    return tb

def dump_qicon_variants(icon: QIcon, basename: str, out_dir: str = "debug_icons", size: QSize = QSize(24, 24)):
    os.makedirs(out_dir, exist_ok=True)

    modes = {
        "normal": QIcon.Normal,
        "active": QIcon.Active,
        "selected": QIcon.Selected,
        "disabled": QIcon.Disabled,
    }
    states = {
        "off": QIcon.Off,
        "on": QIcon.On,
    }

    for mode_name, mode in modes.items():
        for state_name, state in states.items():
            pm = icon.pixmap(size, mode, state)
            path = os.path.join(out_dir, f"{basename}_{mode_name}_{state_name}_{size.width()}x{size.height()}.png")
            ok = pm.save(path, "PNG")
            print("saved" if ok else "FAILED", path)

    
class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        print("block exists:", QFile(":/icons/block.svg").exists())
        print("target exists:", QFile(":/icons/target.svg").exists())
        # optional (hilft zum Testen, ob überhaupt ein Fenster kommt):
        self.setWindowTitle("SmartTScope")

        # Status-Text links
        self.statusText = QLabel("Ready")
        self.statusText.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.statusBar().addWidget(self.statusText, 1)

        # Icons (rot/grün) auf Actions setzen
        size = QSize(18, 18)
        dpr = self.devicePixelRatioF()

        bind_action_red_green(self.ui.actionIndiConnected,  ":/icons/block.svg",        size, dpr)
        bind_action_red_green(self.ui.actionMountUnparked,  ":/icons/sync_disabled.svg", size, dpr)
        bind_action_red_green(self.ui.actionTrackingOn,     ":/icons/target.svg",       size, dpr)

        tb_indi  = _mk_status_tb(self.ui.actionIndiConnected)
        tb_mount = _mk_status_tb(self.ui.actionMountUnparked)
        tb_track = _mk_status_tb(self.ui.actionTrackingOn)

        grp = QWidget()
        lay = QHBoxLayout(grp)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(tb_indi)
        lay.addWidget(tb_mount)
        lay.addWidget(tb_track)

        self.statusBar().addPermanentWidget(grp)

        # Test: Tracking an => grün
        self.ui.actionTrackingOn.setChecked(True)


        size = QSize(18, 18)
        dpr = self.devicePixelRatioF()

##        ic = make_two_state_icon(":/icons/target.svg", size, dpr)
##        dump_qicon_variants(ic, "target", size=size)

        icon_red   = make_two_state_icon(":/icons/target.svg", size, dpr, off="#d32f2f", on="#d32f2f")
        icon_green = make_two_state_icon(":/icons/target.svg", size, dpr, off="#2e7d32", on="#2e7d32")

        
        self.ui.actionIndiConnected.setCheckable(True)
        self.ui.actionIndiConnected.setIcon(make_two_state_icon(":/icons/block.svg", size, dpr))

        self.ui.actionMountUnparked.setCheckable(True)
        self.ui.actionMountUnparked.setIcon(make_two_state_icon(":/icons/sync_disabled.svg", size, dpr))

        self.ui.actionTrackingOn.setCheckable(True)
        self.ui.actionTrackingOn.setChecked(True)   # sollte On-State aktivieren
        print("checked?", self.ui.actionTrackingOn.isChecked())
        self.ui.actionTrackingOn.setIcon(make_two_state_icon(":/icons/target.svg", size, dpr))
        act = self.ui.actionTrackingOn
        act.setCheckable(True)

        def sync_icon(checked: bool):
            act.setIcon(icon_green if checked else icon_red)

        act.toggled.connect(sync_icon)
        sync_icon(act.isChecked())


        # display no signal if required
        for w in (self.ui.camera2View, self.ui.camera3View):
            w.setStyleSheet("background: #111; border: 1px solid #444;")

        # Beispiel Overlay
        self.ui.camera1View.circles = [(320, 240, 40), (320, 240, 80), (320, 240, 120)]

        # Testbild vorberechen
        self._base = self._test_frame(640, 400)

#        self.camera1View.set_frame_u8(img)

        # redraw circles all 100 ms
        self._t = 0

        def blink():
            act.setChecked(not act.isChecked())

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(blink)
        self._blink_timer.start(500)

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)

##        tbTracking = QToolButton()
##        tbTracking.setCheckable(True)
##        tbTracking.setIconSize(QSize(18, 18))
####        print(os.getcwd())
##        icons_tracking = RedGreenIcons(":/icons/target.svg", tbTracking.iconSize())
##        bind_red_green(tbTracking, icons_tracking)
##        apply_red_green_icon(tbTracking, ":/icons/target.svg")

        tb_indi = _mk_status_tb(self.ui.actionIndiConnected)
        tb_mount = _mk_status_tb(self.ui.actionMountUnparked)
        self.tb_track = _mk_status_tb(self.ui.actionTrackingOn)
        tb = QToolButton()
        tb.setDefaultAction(self.ui.actionTrackingOn)

        grp = QWidget()
        lay = QHBoxLayout(grp)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lay.addWidget(tb_indi)
        lay.addWidget(tb_mount)
        lay.addWidget(self.tb_track)
##        lay.addWidget(self.tb)

##        self.ui.statusbar.addPermanentWidget(grp)
##
##        for act in (self.ui.actionIndiConnected, self.ui.actionMountUnparked, self.ui.actionTrackingOn):
##            tb = QToolButton()
##            tb.setDefaultAction(act)
##            tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
##            tb.setAutoRaise(True)
##            tb.setIconSize(size)
##
##            # Anzeige-only, aber NICHT disabled (sonst grau)
##            tb.setAttribute(Qt.WA_TransparentForMouseEvents, True)
##            tb.setFocusPolicy(Qt.NoFocus)
##
##            lay.addWidget(tb)
##
##        self.statusBar().addPermanentWidget(grp)

        # Test
        self.ui.actionTrackingOn.setChecked(True)


    def _tick(self):
        self._t = (self._t + 5) % 255
        img = (self._test_frame() + self._t).astype(np.uint8)
        self.ui.camera1View.set_frame_u8(img)
##        self.ui.statusText.setText(f"INDI connected, tracking on {self._t}")
##        self.ui.statusLog.setText("Mount: unparked • Slew done")
        self.ui.statusbar.showMessage("Connected to INDI", 3000)
        if self.tb_track.isChecked():
            self.tb_track.setToolTip("Uncheck it")
        else:
            self.tb_track.setToolTip("Check it")
        self.tb_track.setEnabled(True)
        self.tb_track.setChecked(not self.tb_track.isChecked())
##        self.tb_track.setCheckable(True)
##        self.tb_track.setIconSize(QSize(18, 18))
##        apply_red_green_icon(self.tb_track, ":/icons/target.svg")
##        action.setChecked(True/False) und/oder
##
##        action.setIcon(QIcon(":/icons/..."))
##
##        action.setToolTip("...")

    # test overlay
    def _test_frame(self, w=640, h=480):
        # einfacher Gradient
        x = np.linspace(0, 255, w, dtype=np.uint8)
        img = np.repeat(x[None, :], h, axis=0)
        return img



def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
