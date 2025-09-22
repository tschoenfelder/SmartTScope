# SmartTScope

Modular Qt UI for Raspberry Pi cameras and devices (telescope, GPS, heater) with Ports/Adapter architecture and TDD-first design.

## Features
- PySide6 desktop UI showing one or two camera streams with high FPS
- Clean **Ports & Adapters** (Hexagonal) architecture
- Hardware-independent tests (Mock camera)
- Optional adapters: OpenCV (Windows dev), Picamera2 (Raspberry Pi)
- Ready-to-run CI, linting (ruff), type-checks (mypy)

## Quickstart

### Windows (dev/TDD)
```bash
pip install -e .[dev,win]
set SMARTTSCOPE_CAMERA=opencv  # or mock
smarttscope
```

### Raspberry Pi (integration)
```bash
sudo apt update
sudo apt install -y python3-picamera2 libcamera-apps
pip install -e .[rpi]
export SMARTTSCOPE_CAMERA=picamera2
smarttscope
```

### Run tests
```bash
pytest -m "not integration"
# on Raspberry Pi:
pytest -m integration
```

See `examples/dual_camera.py` and `configs/*.yaml` for configuration ideas.
