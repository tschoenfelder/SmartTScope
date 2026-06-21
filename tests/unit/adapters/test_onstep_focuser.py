"""Tests for adapters/onstep/focuser.py — OnStepFocuser via mocked serial bus."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.adapters.onstep.focuser import OnStepFocuser
from smart_telescope.adapters.onstep.serial_bus import OnStepSerialBus
from smart_telescope.adapters.onstep.safety import OnStepSafetyConfig, OnStepSafetyError


def _make_bus(replies: dict[str, str] | None = None) -> OnStepSerialBus:
    """Return an OnStepSerialBus whose send() returns values from *replies*."""
    bus = MagicMock(spec=OnStepSerialBus)
    if replies:
        def _send(cmd: str) -> str:
            for key, val in replies.items():
                if cmd.startswith(key):
                    return val
            return ""
        bus.send.side_effect = _send
    else:
        bus.send.return_value = "1"
    return bus


def _make_safety(
    *,
    focuser_min_position: int = 0,
    focuser_max_position: int = 50_000,
) -> OnStepSafetyConfig:
    cfg = MagicMock(spec=OnStepSafetyConfig)
    cfg.focuser_min_position = focuser_min_position
    cfg.focuser_max_position = focuser_max_position
    return cfg


class TestOnStepFocuserConnect:
    def test_connect_returns_true_when_available(self) -> None:
        bus = _make_bus({":FA": "1", ":FM": "50000"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        assert f.connect() is True
        assert f.is_available is True

    def test_connect_returns_true_when_not_available(self) -> None:
        # Even when focuser not available, connect() returns True (caller can check is_available)
        bus = _make_bus({":FA": "0", ":FM": "0"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        assert f.connect() is True
        assert f.is_available is False

    def test_connect_already_available_uses_cached(self) -> None:
        bus = _make_bus({":FA": "1", ":FM": "50000", ":FG": "25000"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        f.connect()
        initial_calls = bus.send.call_count
        f.connect()  # second connect — should not re-probe FA
        # :FA should not be called again
        fa_calls = sum(1 for c in bus.send.call_args_list if c.args[0].startswith(":FA"))
        assert fa_calls == 1

    def test_connect_sets_max_position_from_bus(self) -> None:
        bus = _make_bus({":FA": "1", ":FM": "40000"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        f.connect()
        assert f.get_max_position() == 40000


class TestOnStepFocuserGetters:
    def test_get_position_returns_int(self) -> None:
        bus = _make_bus({":FG": "12345"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        assert f.get_position() == 12345

    def test_get_position_returns_zero_on_invalid_reply(self) -> None:
        bus = _make_bus({":FG": "ERR"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        assert f.get_position() == 0

    def test_is_moving_true_when_reply_is_M(self) -> None:
        bus = _make_bus({":FT": "M"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        assert f.is_moving() is True

    def test_is_moving_false_otherwise(self) -> None:
        bus = _make_bus({":FT": "S"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        assert f.is_moving() is False

    def test_disconnect_is_safe(self) -> None:
        bus = _make_bus()
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        f.disconnect()  # no-op, should not raise


class TestOnStepFocuserStatus:
    def test_status_when_not_available(self) -> None:
        bus = _make_bus()
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        s = f.status()
        assert s.available is False
        assert s.position == 0
        assert s.moving is False

    def test_status_when_available(self) -> None:
        bus = _make_bus({":FA": "1", ":FM": "50000", ":FG": "10000", ":FT": "S"})
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        f.connect()
        s = f.status()
        assert s.available is True
        assert s.position == 10000


class TestOnStepFocuserMove:
    def test_move_absolute_accepts_valid_position(self) -> None:
        bus = MagicMock(spec=OnStepSerialBus)
        bus.send.return_value = "1"
        bus.send_fixed.return_value = "1"
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        f._available = True
        f._max_position = 50_000
        result = f.move_absolute(25_000)
        assert result.accepted is True
        assert result.target_position == 25_000

    def test_move_absolute_raises_on_too_high(self) -> None:
        bus = _make_bus()
        f = OnStepFocuser(bus=bus, safety_config=_make_safety(focuser_max_position=50_000))
        f._max_position = 50_000
        with pytest.raises(OnStepSafetyError):
            f.move_absolute(60_000)

    def test_move_absolute_raises_on_too_low(self) -> None:
        bus = _make_bus()
        f = OnStepFocuser(bus=bus, safety_config=_make_safety(focuser_min_position=100))
        f._max_position = 50_000
        with pytest.raises(OnStepSafetyError):
            f.move_absolute(50)

    def test_move_absolute_raises_on_bus_rejection(self) -> None:
        bus = MagicMock(spec=OnStepSerialBus)
        bus.send.return_value = "1"
        bus.send_fixed.return_value = "0"  # rejected
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        f._available = True
        f._max_position = 50_000
        with pytest.raises(OnStepSafetyError):
            f.move_absolute(25_000)

    def test_move_delegates_to_move_absolute(self) -> None:
        bus = MagicMock(spec=OnStepSerialBus)
        bus.send.return_value = "1"
        bus.send_fixed.return_value = "1"
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        f._available = True
        f._max_position = 50_000
        f.move(25_000)  # should not raise
        bus.send_fixed.assert_called_once()

    def test_stop_calls_write_bypass(self) -> None:
        bus = MagicMock(spec=OnStepSerialBus)
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        f.stop()
        bus.write_bypass.assert_called_once_with(b":FQ#")


class TestOnStepFocuserCalibration:
    def test_set_calibrated_max_position(self) -> None:
        bus = _make_bus()
        f = OnStepFocuser(bus=bus, safety_config=_make_safety(focuser_min_position=100))
        result = f.set_calibrated_max_position(30_000)
        assert result == 30_000
        assert f.get_max_position() == 30_000

    def test_load_calibrated_max_returns_zero_when_file_missing(self, tmp_path: Path) -> None:
        bus = _make_bus()
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        with patch("smart_telescope.config.APP_STATE_DIR", str(tmp_path)):
            result = f._load_calibrated_max_position()
        assert result == 0

    def test_load_calibrated_max_reads_json(self, tmp_path: Path) -> None:
        import json
        calib_file = tmp_path / "onstep_focuser_calibration.json"
        calib_file.write_text(json.dumps({"max_position": 45_000}), encoding="utf-8")
        bus = _make_bus()
        f = OnStepFocuser(bus=bus, safety_config=_make_safety())
        with patch("smart_telescope.config.APP_STATE_DIR", str(tmp_path)):
            result = f._load_calibrated_max_position()
        assert result == 45_000
