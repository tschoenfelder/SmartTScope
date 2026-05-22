"""Native ToupTek standalone filter wheel adapter."""

from __future__ import annotations

import time
from typing import Any

_FLAG_FILTERWHEEL = 0x0000100000000000
_OPTION_FILTERWHEEL_SLOT = 0x48
_OPTION_FILTERWHEEL_POSITION = 0x49


class TouptekFilterWheel:
    def __init__(
        self,
        wheel_id: str | None = None,
        model: str | None = None,
        name: str | None = None,
        settle_s: float = 0.5,
    ) -> None:
        self._wheel_id_hint = wheel_id
        self._model_selector = model
        self._name_selector = name
        self._settle_s = max(0.0, settle_s)
        self._tc: Any = None
        self._handle: Any = None
        self._wheel_id = ""
        self._name = ""
        self._model = ""
        self._slots = 0

    def connect(self) -> bool:
        if self._handle is not None:
            return True
        try:
            import toupcam as tc
        except ImportError:
            return False
        self._tc = tc
        wheels = self.list_wheels()
        wheel = self._select_wheel(wheels)
        if wheel is None:
            listing = ", ".join(item["name"] for item in wheels) or "none"
            raise RuntimeError(f"No ToupTek filter wheel matched selector; found: {listing}")
        handle = tc.Toupcam.Open(wheel["id"])
        if handle is None:
            raise RuntimeError(f"Could not open ToupTek filter wheel {wheel['name']}")
        self._handle = handle
        self._wheel_id = wheel["id"]
        self._name = wheel["name"]
        self._model = wheel["model"]
        self._slots = int(self._try(lambda: handle.get_Option(_opt(tc, "TOUPCAM_OPTION_FILTERWHEEL_SLOT", _OPTION_FILTERWHEEL_SLOT))) or wheel["slots"] or 0)
        return True

    def disconnect(self) -> None:
        if self._handle is not None:
            self._handle.Close()
        self._handle = None

    def list_wheels(self) -> list[dict[str, Any]]:
        try:
            import toupcam as tc
        except ImportError:
            return []
        wheels: list[dict[str, Any]] = []
        for dev in tc.Toupcam.EnumV2():
            flag = int(getattr(dev.model, "flag", 0))
            if not flag & _FLAG_FILTERWHEEL:
                continue
            wheels.append(
                {
                    "id": str(dev.id),
                    "name": str(dev.displayname or dev.model.name),
                    "model": str(dev.model.name),
                    "slots": 0,
                }
            )
        return wheels

    def get_position(self) -> int | None:
        if self._handle is None or self._tc is None:
            raise RuntimeError("Filter wheel not connected")
        value = self._try(lambda: self._handle.get_Option(_opt(self._tc, "TOUPCAM_OPTION_FILTERWHEEL_POSITION", _OPTION_FILTERWHEEL_POSITION)))
        if value is None or int(value) < 0:
            return None
        return int(value) + 1

    def set_position(self, position: int) -> None:
        if position < 1:
            raise ValueError("Filter position is 1-based and must be >= 1")
        if self._handle is None or self._tc is None:
            raise RuntimeError("Filter wheel not connected")
        self._handle.put_Option(
            _opt(self._tc, "TOUPCAM_OPTION_FILTERWHEEL_POSITION", _OPTION_FILTERWHEEL_POSITION),
            int(position) - 1,
        )
        if self._settle_s:
            time.sleep(self._settle_s)

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def wheel_id(self) -> str:
        return self._wheel_id

    @property
    def slots(self) -> int:
        return self._slots

    def _select_wheel(self, wheels: list[dict[str, Any]]) -> dict[str, Any] | None:
        if self._wheel_id_hint:
            for wheel in wheels:
                if wheel["id"] == self._wheel_id_hint:
                    return wheel
        selector = self._name_selector or self._model_selector
        if selector:
            needle = _norm(selector)
            for wheel in wheels:
                if needle in _norm(f"{wheel['name']} {wheel['model']}"):
                    return wheel
        return wheels[0] if wheels else None

    def _try(self, fn: Any) -> Any:
        try:
            return fn()
        except Exception:
            return None


def _norm(value: str) -> str:
    return value.upper().replace(" ", "").replace("_", "")


def _opt(module: Any, name: str, fallback: int) -> int:
    return int(getattr(module, name, fallback))

