from abc import ABC, abstractmethod


class StoragePort(ABC):
    @abstractmethod
    def has_free_space(self) -> bool: ...

    @abstractmethod
    def save_image(self, image_data: bytes, session_id: str) -> str:
        """Persist the stacked image. Returns the absolute path written."""
        ...

    @abstractmethod
    def save_log(self, session_log: dict[str, object], session_id: str) -> str:
        """Persist the session log JSON. Returns the absolute path written.
        Note: the stored dict will not contain its own log path (inherent self-reference).
        """
        ...
