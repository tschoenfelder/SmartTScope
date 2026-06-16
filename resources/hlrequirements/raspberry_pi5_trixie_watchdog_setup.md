# Raspberry Pi 5 / Trixie Watchdog Setup for USB-Control Applications

## Purpose

This document describes a layered watchdog setup for a **Raspberry Pi 5 running Raspberry Pi OS / Debian Trixie 64-bit** where a USB-connected device should receive a defined `STOP` command when the control software fails.

Important limitation:

> A Raspberry Pi that has already crashed hard cannot reliably send a USB command anymore.  
> The Raspberry Pi watchdog can reboot the Pi, but it cannot guarantee that a `STOP` command is transmitted after a kernel freeze, USB-stack failure, or power loss.

Therefore the recommended setup has two parts:

1. **Internal Raspberry Pi watchdog**  
   Reboots the Pi if Linux or `systemd` stops responding.

2. **Application/service watchdog**  
   Detects a hung control process and sends `STOP` while Linux is still alive.

For a safety-relevant STOP behavior, add the external heartbeat supervisor described in the companion file:

```text
external_heartbeat_stop_supervisor.md
```

---

## Target Architecture

```text
Raspberry Pi 5
  ├─ USB control process
  │   ├─ sends normal control commands
  │   ├─ sends STOP during clean shutdown
  │   └─ sends systemd watchdog keepalives
  │
  ├─ systemd service watchdog
  │   ├─ restarts failed control process
  │   └─ runs ExecStopPost= STOP fallback
  │
  └─ hardware watchdog
      └─ reboots the Pi if systemd/kernel stops responding
```

This improves recovery and handles many software failures, but it is not sufficient as the only protection if the external device must be stopped when the Pi itself crashes.

---

## 1. Enable the Raspberry Pi Hardware Watchdog

On Raspberry Pi OS Bookworm/Trixie, the firmware configuration file is normally:

```bash
/boot/firmware/config.txt
```

Edit it:

```bash
sudo nano /boot/firmware/config.txt
```

Add this line:

```ini
dtparam=watchdog=on
```

Reboot:

```bash
sudo reboot
```

After reboot, check whether the watchdog device exists:

```bash
ls -l /dev/watchdog*
```

Expected example:

```text
/dev/watchdog
/dev/watchdog0
```

On some recent Raspberry Pi OS images, the watchdog device may already appear without the explicit `dtparam=watchdog=on`. Keeping the line explicit is still useful because it documents the intended configuration.

---

## 2. Let systemd Feed the Hardware Watchdog

Create a systemd manager configuration drop-in:

```bash
sudo mkdir -p /etc/systemd/system.conf.d

sudo tee /etc/systemd/system.conf.d/10-watchdog.conf >/dev/null <<'EOF_SYSTEMD'
[Manager]
RuntimeWatchdogSec=10s
RebootWatchdogSec=2min
EOF_SYSTEMD
```

Reload systemd itself:

```bash
sudo systemctl daemon-reexec
```

Check the active watchdog settings:

```bash
systemctl show | grep -i watchdog
```

Useful values to look for:

```text
RuntimeWatchdogUSec=10s
RebootWatchdogUSec=2min
```

Notes:

- `RuntimeWatchdogSec=10s` means systemd opens `/dev/watchdog` and periodically feeds it.
- If systemd or the kernel becomes unable to feed the watchdog, the Pi should reboot.
- Use conservative timeouts on Raspberry Pi. Values around **10 s** are usually safer than large values because not every hardware watchdog supports every timeout value.
- This does **not** send `STOP`. It only resets the Pi.

---

## 3. Install Required Packages for a Python-Based USB Control Service

For a Python control process using USB serial and systemd watchdog notifications:

```bash
sudo apt update
sudo apt install python3-serial python3-systemd
```

Create an application directory:

```bash
sudo mkdir -p /opt/usb-control
sudo chown "$USER":"$USER" /opt/usb-control
```

---

## 4. Identify the USB Device Reliably

Avoid unstable names such as `/dev/ttyUSB0` if possible. Use `/dev/serial/by-id/`:

```bash
ls -l /dev/serial/by-id/
```

Example:

```text
usb-FTDI_FT232R_USB_UART_A10ABCDE-if00-port0 -> ../../ttyUSB0
```

Use the full `/dev/serial/by-id/...` path in your scripts and services.

Recommended convention:

```bash
USB_TARGET_PORT="/dev/serial/by-id/usb-your-device-id-if00-port0"
```

---

## 5. Create a Minimal STOP Sender

Create:

```bash
nano /opt/usb-control/send_stop.py
```

Content:

```python
#!/usr/bin/env python3

"""Send a STOP command to a USB serial target.

This script is intended for systemd ExecStop= / ExecStopPost= usage.
It should be short, robust, and independent from the main application.
"""

import sys
from pathlib import Path

import serial

USB_TARGET_PORT = "/dev/serial/by-id/usb-your-device-id-if00-port0"
BAUDRATE = 115200
STOP_COMMAND = b"STOP\n"
SERIAL_TIMEOUT_SECONDS = 1.0


def main() -> int:
    device_path = Path(USB_TARGET_PORT)
    if not device_path.exists():
        print(f"USB target not found: {USB_TARGET_PORT}", file=sys.stderr)
        return 2

    try:
        with serial.Serial(
            USB_TARGET_PORT,
            BAUDRATE,
            timeout=SERIAL_TIMEOUT_SECONDS,
            write_timeout=SERIAL_TIMEOUT_SECONDS,
        ) as port:
            port.write(STOP_COMMAND)
            port.flush()
    except Exception as exc:
        print(f"Failed to send STOP: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Make it executable:

```bash
chmod +x /opt/usb-control/send_stop.py
```

Test it manually while the external target is in a safe state:

```bash
/opt/usb-control/send_stop.py
```

---

## 6. Create a systemd-Watchdog-Aware Control Daemon

Create:

```bash
nano /opt/usb-control/usb_control_daemon.py
```

Content:

```python
#!/usr/bin/env python3

"""Example USB control daemon with systemd watchdog support.

This example periodically notifies systemd that it is alive.
On normal shutdown it sends STOP to the target.

For real use, replace the placeholder loop with the actual USB control logic.
"""

import signal
import sys
import time
from pathlib import Path

import serial
from systemd.daemon import notify

USB_TARGET_PORT = "/dev/serial/by-id/usb-your-device-id-if00-port0"
BAUDRATE = 115200
STOP_COMMAND = b"STOP\n"
SERIAL_TIMEOUT_SECONDS = 1.0
WATCHDOG_NOTIFY_INTERVAL_SECONDS = 1.0

running = True


def request_shutdown(signum, frame):
    global running
    running = False


def send_stop(port: serial.Serial) -> None:
    port.write(STOP_COMMAND)
    port.flush()


def main() -> int:
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    device_path = Path(USB_TARGET_PORT)
    if not device_path.exists():
        print(f"USB target not found: {USB_TARGET_PORT}", file=sys.stderr)
        return 2

    with serial.Serial(
        USB_TARGET_PORT,
        BAUDRATE,
        timeout=SERIAL_TIMEOUT_SECONDS,
        write_timeout=SERIAL_TIMEOUT_SECONDS,
    ) as port:
        notify("READY=1")

        try:
            while running:
                # Replace this with actual application work.
                # Example: read target state, send control commands, check sensors.

                notify("WATCHDOG=1")
                time.sleep(WATCHDOG_NOTIFY_INTERVAL_SECONDS)

        finally:
            # Works during normal service stop or controlled process shutdown.
            # Does not work if the whole Pi is already frozen or powered off.
            try:
                send_stop(port)
            except Exception as exc:
                print(f"Failed to send STOP during shutdown: {exc}", file=sys.stderr)
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Make it executable:

```bash
chmod +x /opt/usb-control/usb_control_daemon.py
```

---

## 7. Create the systemd Service

Create:

```bash
sudo nano /etc/systemd/system/usb-control.service
```

Content:

```ini
[Unit]
Description=USB control service with watchdog and STOP fallback
After=multi-user.target

[Service]
Type=notify
NotifyAccess=main

ExecStart=/usr/bin/python3 /opt/usb-control/usb_control_daemon.py
ExecStop=/usr/bin/python3 /opt/usb-control/send_stop.py
ExecStopPost=/usr/bin/python3 /opt/usb-control/send_stop.py

Restart=on-failure
RestartSec=2s

WatchdogSec=5s

StartLimitIntervalSec=60
StartLimitBurst=3
StartLimitAction=reboot-force

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now usb-control.service
```

Check status:

```bash
systemctl status usb-control.service
```

Follow logs:

```bash
journalctl -u usb-control.service -f
```

---

## 8. Test the Failure Modes

Only test with the external hardware in a safe state.

### Test 1: Normal stop

```bash
sudo systemctl stop usb-control.service
```

Expected behavior:

- The daemon exits.
- `ExecStop=` / `ExecStopPost=` calls `send_stop.py`.
- The USB target receives `STOP`.

Restart afterwards:

```bash
sudo systemctl start usb-control.service
```

---

### Test 2: Process crash

Find the process:

```bash
pgrep -af usb_control_daemon.py
```

Kill it:

```bash
sudo pkill -f usb_control_daemon.py
```

Expected behavior:

- systemd detects process failure.
- systemd runs stop handling.
- The service restarts because `Restart=on-failure` is configured.

Check:

```bash
systemctl status usb-control.service
journalctl -u usb-control.service -n 50
```

---

### Test 3: Application hang

To test `WatchdogSec=`, temporarily modify the daemon so it stops calling:

```python
notify("WATCHDOG=1")
```

Then restart the service:

```bash
sudo systemctl restart usb-control.service
```

Expected behavior:

- systemd waits for the configured watchdog timeout.
- systemd considers the service failed.
- systemd stops/restarts the service.
- `ExecStopPost=` should run the STOP fallback.

Restore the original daemon afterwards.

---

### Test 4: Full Pi freeze or kernel crash

Do not test this on connected hardware unless the external device is safe.

Expected behavior of the internal watchdog:

- The Pi reboots.

Important:

- A full Pi crash does **not** guarantee that `STOP` is sent.
- This is why an external heartbeat supervisor is required for safety-relevant STOP behavior.

---

## 9. Recommended Timeout Values

Suggested starting values:

| Layer | Timeout | Reason |
|---|---:|---|
| Application heartbeat loop | 1 s | Fast detection by external supervisor |
| systemd `WatchdogSec` | 5 s | Detects hung control process |
| systemd `RuntimeWatchdogSec` | 10 s | Reboots Pi if systemd/kernel stop responding |
| External supervisor timeout | 3–5 s | Sends STOP if Pi heartbeat disappears |

Adjust these only after observing real behavior. Avoid setting watchdogs so aggressively that normal CPU or I/O load causes false triggers.

---

## 10. Operational Checklist

Before considering the setup reliable, verify:

- [ ] `/dev/watchdog` and/or `/dev/watchdog0` exists.
- [ ] `systemctl show | grep -i watchdog` shows the expected runtime watchdog setting.
- [ ] USB target path uses `/dev/serial/by-id/...`, not `/dev/ttyUSB0`.
- [ ] `send_stop.py` works manually.
- [ ] `systemctl stop usb-control.service` sends STOP.
- [ ] killing the control process causes restart and STOP fallback.
- [ ] disabling `notify("WATCHDOG=1")` triggers systemd service recovery.
- [ ] external supervisor sends or executes STOP when Pi heartbeat disappears.
- [ ] the system has been tested with the real power supply, USB hub, and target hardware.

---

## 11. References

- Raspberry Pi documentation, `config.txt`:  
  https://www.raspberrypi.com/documentation/computers/config_txt.html

- systemd system manager watchdog settings:  
  https://www.freedesktop.org/software/systemd/man/systemd-system.conf.html

- systemd service unit documentation:  
  https://www.freedesktop.org/software/systemd/man/systemd.service.html

- systemd `sd_notify` documentation:  
  https://www.freedesktop.org/software/systemd/man/sd_notify.html
