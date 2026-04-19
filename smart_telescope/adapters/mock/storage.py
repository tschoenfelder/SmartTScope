from ...ports.storage import StoragePort


class MockStorage(StoragePort):
    def __init__(self, disk_full: bool = False) -> None:
        self._disk_full = disk_full
        self.saved_image: bytes = b""
        self.saved_log: dict = {}

    def has_free_space(self) -> bool:
        return not self._disk_full

    def save_image(self, image_data: bytes, session_id: str) -> str:
        self.saved_image = image_data
        return "/mock/session_result.png"

    def save_log(self, session_log: dict, session_id: str) -> str:
        self.saved_log = session_log
        return "/mock/session_log.json"
