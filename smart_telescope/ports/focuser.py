from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class FocuserStatus:
    available: bool
    position: int
    max_position: int
    moving: bool


@dataclass(frozen=True)
class FocuserMoveResult:
    accepted: bool
    target_position: int
    start_position: int
    onstep_reply: str


class FocuserPort(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def status(self) -> FocuserStatus: ...

    @abstractmethod
    def move_absolute(self, steps: int) -> FocuserMoveResult: ...

    @abstractmethod
    def move(self, steps: int) -> None: ...

    @abstractmethod
    def get_position(self) -> int: ...

    @abstractmethod
    def get_max_position(self) -> int: ...

    @abstractmethod
    def is_moving(self) -> bool: ...

    @abstractmethod
    def stop(self) -> None: ...

    @property
    @abstractmethod
    def is_available(self) -> bool: ...
