from ...ports.storage import StoragePort, SavedArtifacts


class MockStorage(StoragePort):
    def __init__(self, disk_full: bool = False) -> None:
        self._disk_full = disk_full
        self.saved_image: bytes = b""
        self.saved_log: dict = {}

    def has_free_space(self) -> bool:
        return not self._disk_full

    def save(self, image_data: bytes, session_log: dict) -> SavedArtifacts:
        self.saved_image = image_data
        self.saved_log = session_log
        return SavedArtifacts(
            image_path="/mock/session_result.png",
            log_path="/mock/session_log.json",
        )
