from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SavedArtifacts:
    image_path: str
    log_path: str


class StoragePort(ABC):
    @abstractmethod
    def has_free_space(self) -> bool: ...

    @abstractmethod
    def save(self, image_data: bytes, session_log: dict) -> SavedArtifacts: ...
