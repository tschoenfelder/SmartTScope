# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'SmartTScope.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt, QTimer)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QMainWindow, QMenuBar,
    QSizePolicy, QStatusBar, QVBoxLayout, QWidget)
import numpy as np

from ui_smarttscope import Ui_MainWindow

from widgets.overlayimagewidget import OverlayImageWidget
import resources_rc

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        for w in (self.ui.camera1View, self.ui.camera2View, self.ui.camera3View):
            w.setStyleSheet("background: #111; border: 1px solid #444;")

        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1112, 889)
        self.actionIndiConnected = QAction(MainWindow)
        self.actionIndiConnected.setObjectName(u"actionIndiConnected")
        self.actionIndiConnected.setCheckable(True)
        icon = QIcon()
        icon.addFile(u":/icons/icons/block_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.actionIndiConnected.setIcon(icon)
        self.actionMountUnparked = QAction(MainWindow)
        self.actionMountUnparked.setObjectName(u"actionMountUnparked")
        self.actionMountUnparked.setCheckable(True)
        icon1 = QIcon()
        icon1.addFile(u":/icons/icons/sync_disabled_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        icon1.addFile(u":/icons/icons/sync_disabled_24dp_1F1F1F_FILL0_wght400_GRAD0_opsz24.svg", QSize(), QIcon.Mode.Normal, QIcon.State.On)
        self.actionMountUnparked.setIcon(icon1)
        self.actionTrackingOn = QAction(MainWindow)
        self.actionTrackingOn.setObjectName(u"actionTrackingOn")
        self.actionTrackingOn.setCheckable(True)
        icon2 = QIcon()
        icon2.addFile(u":/icons/icons/target.svg", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        self.actionTrackingOn.setIcon(icon2)
        self.MainContainer = QWidget(MainWindow)
        self.MainContainer.setObjectName(u"MainContainer")
        self.verticalLayout = QVBoxLayout(self.MainContainer)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(4)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.camera1View = OverlayImageWidget(self.MainContainer)
        self.camera1View.setObjectName(u"camera1View")
        self.camera1View.setMinimumSize(QSize(320, 240))

        self.horizontalLayout.addWidget(self.camera1View)

        self.RightCams = QVBoxLayout()
        self.RightCams.setObjectName(u"RightCams")
        self.camera3View = OverlayImageWidget(self.MainContainer)
        self.camera3View.setObjectName(u"camera3View")
        self.camera3View.setMinimumSize(QSize(320, 240))

        self.RightCams.addWidget(self.camera3View)

        self.camera2View = OverlayImageWidget(self.MainContainer)
        self.camera2View.setObjectName(u"camera2View")
        self.camera2View.setMinimumSize(QSize(320, 240))

        self.RightCams.addWidget(self.camera2View)


        self.horizontalLayout.addLayout(self.RightCams)

        self.horizontalLayout.setStretch(0, 2)
        self.horizontalLayout.setStretch(1, 1)

        self.verticalLayout.addLayout(self.horizontalLayout)

        MainWindow.setCentralWidget(self.MainContainer)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1112, 21))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.actionIndiConnected.setText(QCoreApplication.translate("MainWindow", u"actionIndiConnected", None))
        self.actionMountUnparked.setText(QCoreApplication.translate("MainWindow", u"actionMountUnparked", None))
        self.actionTrackingOn.setText(QCoreApplication.translate("MainWindow", u"actionTrackingOn", None))
    # retranslateUi

