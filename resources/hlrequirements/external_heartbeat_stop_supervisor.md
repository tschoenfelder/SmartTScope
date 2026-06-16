# External Heartbeat and STOP Supervisor Setup

## Purpose

This document describes how to design an external watchdog that ensures a controlled device receives or executes a `STOP` action when the Raspberry Pi stops working.

This is required because a crashed Raspberry Pi cannot reliably send a USB command anymore. The external supervisor must be independent enough to detect the missing Raspberry Pi heartbeat and trigger the safe state itself.

---

## Core Principle

```text
Raspberry Pi 5
  └─ sends heartbeat every 1 s

External supervisor
  ├─ receives heartbeat
  ├─ detects timeout after 3–5 s
  └─ sends STOP or activates hardware STOP output

Controlled target
  └─ enters safe state
```

The external supervisor must not wait for the Pi to send `STOP`. It must act when the heartbeat disappears.

---

## 1. Choose the Correct Hardware Architecture

### Preferred Option: Target Implements Its Own Heartbeat Timeout

Best design:

```text
Raspberry Pi → Target device
              └─ target executes STOP if no heartbeat arrives
```

The target device receives a regular heartbeat such as:

```text
HB\n
```

Target rule:

```text
if no heartbeat received for 3–5 seconds:
    execute STOP locally
```

This is the most robust solution because no third device is needed.

---

### Option A: External Microcontroller Supervisor

Use this if the target has a simple STOP input, for example:

- GPIO STOP input
- relay/contact input
- UART command input
- RS-485 command input

Possible supervisors:

- Arduino
- Raspberry Pi Pico
- ESP32
- small industrial watchdog relay

Architecture:

```text
Raspberry Pi 5 ──heartbeat──> Microcontroller ──STOP──> Target
```

This is simple and reliable if the STOP action does not require USB host functionality.

---

### Option B: External USB-Host Supervisor

Use this if the target can only receive STOP via USB.

Architecture:

```text
Raspberry Pi 5 ──heartbeat──> Supervisor with USB host ──USB STOP──> Target
```

Suitable supervisors:

- second Raspberry Pi
- Linux SBC with USB host
- embedded controller with proven USB host support

Important:

> A Raspberry Pi Pico, Arduino, or ESP32 connected to the main Pi as a USB serial device is normally not sufficient to send commands to another USB device.  
> If the STOP command must go over USB to the target, the supervisor must itself act as a USB host for that target.

---

## 2. Define a Simple Heartbeat Protocol

Recommended protocol from the Raspberry Pi to the supervisor:

```text
HB <counter>\n
```

Example:

```text
HB 1
HB 2
HB 3
```

Recommended settings:

| Parameter | Suggested value |
|---|---:|
| Heartbeat interval | 1 s |
| Supervisor timeout | 3–5 s |
| STOP command retry count | 3 |
| STOP retry interval | 250–500 ms |

The supervisor should use a monotonic timer and should not rely on wall-clock time.

---

## 3. Raspberry Pi Heartbeat Sender

This sender runs on the Raspberry Pi and sends the heartbeat to the external supervisor.

Install dependency:

```bash
sudo apt update
sudo apt install python3-serial
```

Create directory:

```bash
sudo mkdir -p /opt/heartbeat-sender
sudo chown "$USER":"$USER" /opt/heartbeat-sender
```

Create:

```bash
nano /opt/heartbeat-sender/heartbeat_sender.py
```

Content:

```python
#!/usr/bin/env python3

"""Send heartbeat messages from the Raspberry Pi to an external supervisor."""

import signal
import sys
import time
from pathlib import Path

import serial

SUPERVISOR_PORT = "/dev/serial/by-id/usb-your-supervisor-id-if00-port0"
BAUDRATE = 115200
HEARTBEAT_INTERVAL_SECONDS = 1.0
SERIAL_TIMEOUT_SECONDS = 1.0

running = True


def request_shutdown(signum, frame):
    global running
    running = False


def main() -> int:
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    device_path = Path(SUPERVISOR_PORT)
    if not device_path.exists():
        print(f"Supervisor port not found: {SUPERVISOR_PORT}", file=sys.stderr)
        return 2

    counter = 0

    with serial.Serial(
        SUPERVISOR_PORT,
        BAUDRATE,
        timeout=SERIAL_TIMEOUT_SECONDS,
        write_timeout=SERIAL_TIMEOUT_SECONDS,
    ) as port:
        while running:
            counter += 1
            message = f"HB {counter}\n".encode("ascii")
            port.write(message)
            port.flush()
            time.sleep(HEARTBEAT_INTERVAL_SECONDS)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Make executable:

```bash
chmod +x /opt/heartbeat-sender/heartbeat_sender.py
```

Test manually:

```bash
/opt/heartbeat-sender/heartbeat_sender.py
```

---

## 4. systemd Service for the Heartbeat Sender

Create:

```bash
sudo nano /etc/systemd/system/heartbeat-sender.service
```

Content:

```ini
[Unit]
Description=Heartbeat sender for external STOP supervisor
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/heartbeat-sender/heartbeat_sender.py
Restart=always
RestartSec=2s

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now heartbeat-sender.service
```

Check:

```bash
systemctl status heartbeat-sender.service
journalctl -u heartbeat-sender.service -f
```

---

## 5. Microcontroller Supervisor Example

This example assumes:

- Raspberry Pi sends heartbeat via UART/USB serial.
- Supervisor activates a hardware STOP output if heartbeat times out.
- STOP output is active-high.

### MicroPython Example for Raspberry Pi Pico / ESP32

```python
from machine import Pin, UART
import time

UART_ID = 0
BAUDRATE = 115200
TIMEOUT_MS = 4000
STOP_PULSE_MS = 1000

# Adjust pins for your board.
# Raspberry Pi Pico example: UART0 TX=GP0, RX=GP1.
uart = UART(UART_ID, baudrate=BAUDRATE)

stop_output = Pin(15, Pin.OUT)
stop_output.value(0)

last_heartbeat_ms = time.ticks_ms()
stop_already_triggered = False


def trigger_stop():
    global stop_already_triggered
    if stop_already_triggered:
        return

    stop_output.value(1)
    time.sleep_ms(STOP_PULSE_MS)
    stop_output.value(0)
    stop_already_triggered = True


while True:
    if uart.any():
        line = uart.readline()
        if line and line.startswith(b"HB"):
            last_heartbeat_ms = time.ticks_ms()
            stop_already_triggered = False

    elapsed_ms = time.ticks_diff(time.ticks_ms(), last_heartbeat_ms)
    if elapsed_ms > TIMEOUT_MS:
        trigger_stop()

    time.sleep_ms(50)
```

This version triggers STOP once after heartbeat loss. After heartbeat resumes, it arms itself again.

---

## 6. Microcontroller Supervisor Sending STOP via UART

If the target accepts a serial command instead of a GPIO signal, use a second UART or serial interface to the target.

Conceptual MicroPython structure:

```python
from machine import UART
import time

heartbeat_uart = UART(0, baudrate=115200)
target_uart = UART(1, baudrate=115200)

TIMEOUT_MS = 4000
STOP_COMMAND = b"STOP\n"
STOP_RETRIES = 3
STOP_RETRY_DELAY_MS = 300

last_heartbeat_ms = time.ticks_ms()
stop_already_triggered = False


def send_stop_to_target():
    global stop_already_triggered
    if stop_already_triggered:
        return

    for _ in range(STOP_RETRIES):
        target_uart.write(STOP_COMMAND)
        time.sleep_ms(STOP_RETRY_DELAY_MS)

    stop_already_triggered = True


while True:
    if heartbeat_uart.any():
        line = heartbeat_uart.readline()
        if line and line.startswith(b"HB"):
            last_heartbeat_ms = time.ticks_ms()
            stop_already_triggered = False

    elapsed_ms = time.ticks_diff(time.ticks_ms(), last_heartbeat_ms)
    if elapsed_ms > TIMEOUT_MS:
        send_stop_to_target()

    time.sleep_ms(50)
```

---

## 7. USB-Only Target: Linux Supervisor Example

Use this if the target only accepts STOP through USB.

Architecture:

```text
Main Raspberry Pi 5 ──UART/USB heartbeat──> second Linux supervisor ──USB STOP──> Target
```

The second Linux supervisor needs two stable device paths:

```text
/dev/serial/by-id/...heartbeat-from-main-pi...
/dev/serial/by-id/...target-usb-device...
```

Example relay script on the supervisor:

```python
#!/usr/bin/env python3

"""External Linux STOP relay.

Receives heartbeat from the main Raspberry Pi.
If heartbeat disappears, sends STOP to the USB target.
"""

import time
from pathlib import Path

import serial

HEARTBEAT_PORT = "/dev/serial/by-id/usb-heartbeat-input"
TARGET_PORT = "/dev/serial/by-id/usb-target-device"
BAUDRATE = 115200
HEARTBEAT_TIMEOUT_SECONDS = 4.0
STOP_COMMAND = b"STOP\n"
STOP_RETRIES = 3
STOP_RETRY_DELAY_SECONDS = 0.3


def send_stop() -> None:
    with serial.Serial(TARGET_PORT, BAUDRATE, timeout=1, write_timeout=1) as target:
        for _ in range(STOP_RETRIES):
            target.write(STOP_COMMAND)
            target.flush()
            time.sleep(STOP_RETRY_DELAY_SECONDS)


def main() -> int:
    if not Path(HEARTBEAT_PORT).exists():
        raise FileNotFoundError(HEARTBEAT_PORT)
    if not Path(TARGET_PORT).exists():
        raise FileNotFoundError(TARGET_PORT)

    last_heartbeat = time.monotonic()
    stop_already_triggered = False

    with serial.Serial(HEARTBEAT_PORT, BAUDRATE, timeout=0.1) as heartbeat:
        while True:
            line = heartbeat.readline()
            if line.startswith(b"HB"):
                last_heartbeat = time.monotonic()
                stop_already_triggered = False

            if time.monotonic() - last_heartbeat > HEARTBEAT_TIMEOUT_SECONDS:
                if not stop_already_triggered:
                    send_stop()
                    stop_already_triggered = True

            time.sleep(0.05)


if __name__ == "__main__":
    raise SystemExit(main())
```

Run this script as a systemd service on the external Linux supervisor.

---

## 8. Wiring Notes

### UART heartbeat

For UART between Raspberry Pi and microcontroller:

- Pi TX → supervisor RX
- Pi GND → supervisor GND
- Use 3.3 V logic only unless level shifting is provided.
- Do not connect 5 V UART signals directly to Raspberry Pi GPIO.

### Hardware STOP output

For switching a STOP input:

- Prefer optocoupler or relay isolation if the target uses a different supply or noisy environment.
- Define the safe state electrically.
- Decide whether STOP is active-high, active-low, pulse-based, or latched.
- Ensure STOP is also triggered if the supervisor itself resets, if required by the safety case.

### USB STOP target

If STOP must be sent via USB:

- The supervisor must have USB host capability.
- Use stable `/dev/serial/by-id/...` paths.
- Test behavior when USB is unplugged/replugged.
- Test behavior when the target resets but the supervisor stays alive.

---

## 9. Test Procedure

### Test 1: Heartbeat visible

On the supervisor, log received heartbeat lines.

Expected:

```text
HB 1
HB 2
HB 3
...
```

---

### Test 2: Stop heartbeat sender

On the Raspberry Pi:

```bash
sudo systemctl stop heartbeat-sender.service
```

Expected:

- Supervisor detects timeout after 3–5 s.
- Supervisor triggers STOP.

Restart:

```bash
sudo systemctl start heartbeat-sender.service
```

---

### Test 3: Kill heartbeat sender

```bash
sudo pkill -f heartbeat_sender.py
```

Expected:

- If systemd restarts the sender quickly enough, the supervisor may not timeout.
- If the downtime exceeds the supervisor timeout, STOP is triggered.

This test validates the timeout margin.

---

### Test 4: Main Pi power loss

Only test with the controlled target in a safe condition.

Expected:

- Heartbeat disappears immediately.
- Supervisor triggers STOP after timeout.

---

### Test 5: USB target unavailable

Disconnect the target from the supervisor and force timeout.

Expected:

- Supervisor logs/reporting show that STOP could not be sent.
- Supervisor retries according to the configured retry policy.
- The failure is visible and not silently ignored.

---

## 10. Recommended Practical Setup

For a STOP command that is truly safety-relevant:

```text
Main Raspberry Pi 5
  ├─ runs normal USB control app
  ├─ sends heartbeat to external supervisor every 1 s
  └─ has internal hardware watchdog for reboot

External supervisor
  ├─ is powered independently or from a protected supply
  ├─ monitors heartbeat timeout of 3–5 s
  ├─ sends STOP or activates STOP output
  └─ logs/report failures if possible

Target device
  └─ enters safe state on STOP
```

Best implementation order:

1. Make manual `STOP` reliable.
2. Make `STOP` work from a short standalone script.
3. Add the Pi-side service watchdog.
4. Add the external heartbeat sender.
5. Add the external supervisor timeout.
6. Test power loss, process crash, service hang, and USB reconnect scenarios.

---

## 11. Design Checklist

- [ ] STOP command is defined and tested manually.
- [ ] STOP command is idempotent, meaning repeated STOP commands are safe.
- [ ] Target enters safe state if STOP is repeated.
- [ ] Heartbeat interval is shorter than the timeout by a clear margin.
- [ ] Supervisor uses monotonic time.
- [ ] Supervisor does not rely on the Pi closing the USB connection.
- [ ] Supervisor can send STOP without assistance from the Pi.
- [ ] Supervisor has its own stable power source if required.
- [ ] USB-only STOP targets are controlled by a USB-host-capable supervisor.
- [ ] All serial devices use stable `/dev/serial/by-id/...` paths.
- [ ] Behavior was tested with realistic power, USB, and load conditions.
