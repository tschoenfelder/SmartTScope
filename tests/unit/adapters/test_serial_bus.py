"""Tests for adapters/onstep/serial_bus.py — thread-safe serial wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.adapters.onstep.serial_bus import OnStepSerialBus


def _make_serial(
    *,
    is_open: bool = True,
    read_data: bytes = b"OK#",
    has_read_until: bool = True,
) -> MagicMock:
    s = MagicMock()
    s.is_open = is_open
    if has_read_until:
        s.read_until.return_value = read_data
    else:
        del s.read_until  # make hasattr() return False
        s.read.return_value = read_data
    return s


class TestIsOpen:
    def test_no_serial_is_not_open(self) -> None:
        bus = OnStepSerialBus()
        assert bus.is_open is False

    def test_serial_open_true(self) -> None:
        bus = OnStepSerialBus()
        bus._serial = _make_serial(is_open=True)
        assert bus.is_open is True

    def test_serial_open_false(self) -> None:
        bus = OnStepSerialBus()
        bus._serial = _make_serial(is_open=False)
        assert bus.is_open is False


class TestClose:
    def test_close_when_none_is_safe(self) -> None:
        bus = OnStepSerialBus()
        bus.close()  # should not raise

    def test_close_calls_serial_close(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        bus._serial = s
        bus.close()
        s.close.assert_called_once()

    def test_close_sets_serial_to_none(self) -> None:
        bus = OnStepSerialBus()
        bus._serial = _make_serial()
        bus.close()
        assert bus._serial is None

    def test_close_suppresses_exception(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        s.close.side_effect = OSError("port gone")
        bus._serial = s
        bus.close()  # should not raise
        assert bus._serial is None


class TestRawSend:
    def test_no_serial_returns_empty_bytes(self) -> None:
        bus = OnStepSerialBus()
        assert bus.raw_send(":GC#") == b""

    def test_sends_command_and_returns_reply(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial(read_data=b"12:00:00#")
        bus._serial = s
        result = bus.raw_send(":GC#")
        s.write.assert_called_once_with(b":GC#")
        assert result == b"12:00:00#"

    def test_uses_read_when_no_read_until(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial(has_read_until=False, read_data=b"1#")
        bus._serial = s
        result = bus.raw_send(":FA#")
        assert result == b"1#"

    def test_clears_serial_on_exception(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        s.write.side_effect = OSError("port error")
        bus._serial = s
        with pytest.raises(OSError):
            bus.raw_send(":GC#")
        assert bus._serial is None


class TestSend:
    def test_decode_and_strip_hash(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial(read_data=b"24:00#")
        bus._serial = s
        result = bus.send(":GC#")
        assert result == "24:00"

    def test_no_serial_returns_empty_str(self) -> None:
        bus = OnStepSerialBus()
        assert bus.send(":GC#") == ""


class TestWriteNoReply:
    def test_no_serial_returns_immediately(self) -> None:
        bus = OnStepSerialBus()
        bus.write_no_reply(":MS#")  # no raise

    def test_sends_command(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        bus._serial = s
        bus.write_no_reply(":MS#")
        s.write.assert_called_once_with(b":MS#")

    def test_raises_timeout_when_lock_busy(self) -> None:
        bus = OnStepSerialBus()
        bus._serial = _make_serial()
        # Acquire lock to simulate busy
        bus._lock.acquire()
        try:
            with pytest.raises(TimeoutError):
                bus.write_no_reply(":MS#", timeout=0.001)
        finally:
            bus._lock.release()

    def test_clears_serial_on_exception(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        s.write.side_effect = OSError("write failed")
        bus._serial = s
        with pytest.raises(OSError):
            bus.write_no_reply(":MS#")
        assert bus._serial is None


class TestSendFixed:
    def test_no_serial_returns_empty(self) -> None:
        bus = OnStepSerialBus()
        assert bus.send_fixed(":MS#") == ""

    def test_reads_fixed_size_reply(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        s.read.return_value = b"1"
        bus._serial = s
        result = bus.send_fixed(":MS#", size=1)
        assert result == "1"

    def test_raises_timeout_when_lock_busy(self) -> None:
        bus = OnStepSerialBus()
        bus._serial = _make_serial()
        bus._lock.acquire()
        try:
            with pytest.raises(TimeoutError):
                bus.send_fixed(":MS#", timeout=0.001)
        finally:
            bus._lock.release()

    def test_clears_serial_on_exception(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        s.write.side_effect = OSError("error")
        bus._serial = s
        with pytest.raises(OSError):
            bus.send_fixed(":MS#")
        assert bus._serial is None


class TestWriteBypass:
    def test_no_serial_is_safe(self) -> None:
        bus = OnStepSerialBus()
        bus.write_bypass(b":Q#")  # no raise

    def test_writes_without_lock(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        bus._serial = s
        bus._lock.acquire()  # lock is held — bypass should still write
        try:
            bus.write_bypass(b":Q#")
        finally:
            bus._lock.release()
        s.write.assert_called_once_with(b":Q#")

    def test_suppresses_write_exception(self) -> None:
        bus = OnStepSerialBus()
        s = _make_serial()
        s.write.side_effect = OSError("hardware gone")
        bus._serial = s
        bus.write_bypass(b":Q#")  # suppressed by contextlib.suppress
