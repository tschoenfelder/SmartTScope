from abc import ABC, abstractmethod


class FocuserPort(ABC):
    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def move(self, steps: int) -> None: ...

    @abstractmethod
    def get_position(self) -> int: ...
