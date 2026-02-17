class CameraProcessor(QtCore.QObject):
    frameReady = QtCore.Signal(object)  # emits np.ndarray uint8 (H,W)

    def __init__(self, stack_n: int):
        super().__init__()
        self.stacker = RollingMeanStacker(stack_n)
        self.black = 0
        self.white = 65535
        self._counter = 0

    @QtCore.Slot(object)
    def feed_frame(self, frame_u16: np.ndarray):
        stacked = self.stacker.push(frame_u16)

        # Option: refresh levels every K frames
        self._counter += 1
        if self._counter % 10 == 0:
            self.black, self.white = auto_levels_u16(stacked)

        preview = to_u8_preview(stacked, self.black, self.white)
        self.frameReady.emit(preview)

# UI wiring
# in main UI setup
self.view = OverlayImageWidget()
self.view.circles = [(320, 240, 40), (320, 240, 80), (320, 240, 120)]  # example

self.proc = CameraProcessor(stack_n=5)
self.thread = QtCore.QThread()
self.proc.moveToThread(self.thread)
self.thread.start()

self.proc.frameReady.connect(self.view.set_frame_u8)

# when a new frame arrives from INDI (in any thread):
# QtCore.QMetaObject.invokeMethod(self.proc, "feed_frame",
#                                QtCore.Qt.QueuedConnection,
#                                QtCore.Q_ARG(object, frame_u16))

##Wichtig: Wenn dein INDI-Callback nicht im Qt-Thread läuft, nutze invokeMethod(... QueuedConnection ...) oder ein Signal, damit Qt die Daten thread-sicher in den Processor schiebt.
##
