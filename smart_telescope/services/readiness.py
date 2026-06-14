"""ReadinessService — synthesizes red/yellow/green readiness from all subsystems.

Checks (in display order):
  config_file   — ~/.SmartTScope/config.toml found
  stars_cfg     — stars.cfg exists at configured path (RED if missing)
  horizon_dat   — horizon file exists (YELLOW if missing)
  storage       — storage directory writable and has space
  astap_exe     — ASTAP binary found (RED if missing)
  astap_catalog — ASTAP star catalog found (RED if missing)
  camera        — at least one camera role configured
  mount         — OnStep port configured and (if connected) responding
  focuser       — focuser available (YELLOW if unavailable)

The overall level is the worst of all items.
can_observe is True when overall is not RED and hardware mode is 'real'.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class Level(str, Enum):
    GREEN  = "green"
    YELLOW = "yellow"
    RED    = "red"


class ReadinessItem(BaseModel):
    key:    str
    label:  str
    level:  Level
    message: str
    repair:  str | None = None


class ReadinessReport(BaseModel):
    overall:       Level
    can_observe:   bool
    can_preview:   bool
    can_goto:      bool
    can_solve:     bool
    can_autofocus: bool
    can_save:      bool
    mode:          str
    items:         list[ReadinessItem]
    checked_at:    str


class ReadinessService:
    @staticmethod
    def _capability_flags(items: list[ReadinessItem]) -> dict[str, bool]:
        """Derive per-feature capability flags from readiness items.

        Only RED items block a capability; YELLOW = degraded but functional.
        """
        red = {i.key for i in items if i.level == Level.RED}
        return {
            "can_preview":   "camera"       not in red,
            "can_goto":      "mount"        not in red,
            "can_solve":     "astap_exe"    not in red and "astap_catalog" not in red,
            "can_autofocus": "focuser"      not in red,
            "can_save":      "storage"      not in red,
        }

    def check(self) -> ReadinessReport:
        mode = self._get_hardware_mode()
        mode_item = self._check_mode(mode)

        items: list[ReadinessItem] = [mode_item]
        items.append(self._check_config_file())
        items.append(self._check_stars_cfg())
        items.append(self._check_horizon_dat())
        items.append(self._check_storage())
        items.extend(self._check_astap())
        items.append(self._check_camera())
        items.extend(self._check_mount_focuser())
        uncfg = self._check_unconfigured_cameras()
        if uncfg is not None:
            items.append(uncfg)

        if any(i.level == Level.RED for i in items):
            overall = Level.RED
        elif any(i.level == Level.YELLOW for i in items):
            overall = Level.YELLOW
        else:
            overall = Level.GREEN

        can_observe = overall != Level.RED and mode == "real"  # mode-gated: simulator/mock cannot observe

        flags = self._capability_flags(items)
        return ReadinessReport(
            overall=overall,
            can_observe=can_observe,
            can_preview=flags["can_preview"],
            can_goto=flags["can_goto"],
            can_solve=flags["can_solve"],
            can_autofocus=flags["can_autofocus"],
            can_save=flags["can_save"],
            mode=mode,
            items=items,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── individual checks ─────────────────────────────────────────────────────

    def _get_hardware_mode(self) -> str:
        try:
            from ..runtime import get_runtime
            return get_runtime().hardware_mode
        except Exception:
            return "mock"

    def _check_mode(self, mode: str) -> ReadinessItem:
        if mode == "real":
            return ReadinessItem(
                key="hardware_mode", label="Hardware mode",
                level=Level.GREEN, message="REAL",
            )
        if mode == "simulator":
            return ReadinessItem(
                key="hardware_mode", label="Hardware mode",
                level=Level.YELLOW, message="SIMULATOR — observation disabled",
                repair="Simulator mode active. Use real hardware to enable observation.",
            )
        return ReadinessItem(
            key="hardware_mode", label="Hardware mode",
            level=Level.YELLOW, message="MOCK — observation disabled",
            repair="Set onstep_port in the [hardware] section of ~/.SmartTScope/config.toml.",
        )

    def _check_config_file(self) -> ReadinessItem:
        from .. import config
        if config._load_error is not None:
            return ReadinessItem(
                key="config_file", label="Configuration file",
                level=Level.RED,
                message=str(config._load_error),
                repair="Fix the TOML syntax error in your config.toml and restart the server.",
            )
        user_cfg = Path.home() / ".SmartTScope" / "config.toml"
        if user_cfg.exists():
            return ReadinessItem(
                key="config_file", label="Configuration file",
                level=Level.GREEN, message=f"Found: {user_cfg}",
            )
        dev_cfg = Path.cwd() / "smart_telescope.toml"
        if dev_cfg.exists():
            return ReadinessItem(
                key="config_file", label="Configuration file",
                level=Level.YELLOW,
                message=f"Using dev config: {dev_cfg}",
                repair="Copy to ~/.SmartTScope/config.toml for a stable installation.",
            )
        return ReadinessItem(
            key="config_file", label="Configuration file",
            level=Level.RED, message="No config.toml found",
            repair="Copy templates/config.toml to ~/.SmartTScope/config.toml and fill in your hardware settings.",
        )

    def _check_stars_cfg(self) -> ReadinessItem:
        from .. import config
        path = Path(config.STARS_CFG) if config.STARS_CFG else None
        if path and path.exists():
            return ReadinessItem(
                key="stars_cfg", label="Stars catalog (stars.cfg)",
                level=Level.GREEN, message=f"Found: {path}",
            )
        return ReadinessItem(
            key="stars_cfg", label="Stars catalog (stars.cfg)",
            level=Level.RED,
            message=f"Not found: {path or '(not configured)'}",
            repair=(
                f"Copy stars.cfg to {path or '~/.SmartTScope/stars.cfg'} "
                f"or set stars_cfg in config.toml."
            ),
        )

    def _check_horizon_dat(self) -> ReadinessItem:
        from .. import config
        path = Path(config.HORIZON_DAT) if config.HORIZON_DAT else None
        if path and path.exists():
            return ReadinessItem(
                key="horizon_dat", label="Horizon file",
                level=Level.GREEN, message=f"Found: {path}",
            )
        return ReadinessItem(
            key="horizon_dat", label="Horizon file",
            level=Level.YELLOW,
            message=f"Not found: {path or '(not configured)'} — using flat 10° horizon",
            repair="Create a horizon profile and set horizon_dat in config.toml.",
        )

    def _check_storage(self) -> ReadinessItem:
        from .. import config
        path_str = config.STORAGE_DIR
        if not path_str:
            return ReadinessItem(
                key="storage", label="Session storage",
                level=Level.YELLOW,
                message="Not configured — captured images will not be saved",
                repair="Set storage_dir in config.toml, e.g. storage_dir = '~/astro'.",
            )
        path = Path(path_str)
        if not path.exists():
            return ReadinessItem(
                key="storage", label="Session storage",
                level=Level.RED,
                message=f"Directory not found: {path}",
                repair=f"Create the directory: mkdir -p {path}",
            )
        if not os.access(path, os.W_OK):
            return ReadinessItem(
                key="storage", label="Session storage",
                level=Level.RED,
                message=f"Directory not writable: {path}",
                repair=f"Fix permissions: chmod u+w {path}",
            )
        usage = shutil.disk_usage(path)
        free_gb = round(usage.free / (1024 ** 3), 1)
        if free_gb < 2:
            return ReadinessItem(
                key="storage", label="Session storage",
                level=Level.RED,
                message=f"Disk nearly full: {free_gb} GB free",
                repair="Free up disk space before starting a session.",
            )
        if free_gb < 10:
            return ReadinessItem(
                key="storage", label="Session storage",
                level=Level.YELLOW,
                message=f"Low disk space: {free_gb} GB free",
                repair="Consider freeing up disk space soon.",
            )
        return ReadinessItem(
            key="storage", label="Session storage",
            level=Level.GREEN,
            message=f"{free_gb} GB free at {path}",
        )

    def _check_astap(self) -> list[ReadinessItem]:
        from ..adapters.astap.solver import find_astap, find_catalog
        astap_path = find_astap()
        if not astap_path:
            return [
                ReadinessItem(
                    key="astap_exe", label="ASTAP plate solver",
                    level=Level.RED, message="ASTAP not found",
                    repair="Install ASTAP and set astap.path in config.toml, or install to /usr/local/bin/astap.",
                ),
                ReadinessItem(
                    key="astap_catalog", label="ASTAP star catalog",
                    level=Level.RED, message="Cannot check — ASTAP not found",
                    repair="Install ASTAP first, then install the H18 or D50 catalog.",
                ),
            ]
        catalog = find_catalog(astap_path)
        return [
            ReadinessItem(
                key="astap_exe", label="ASTAP plate solver",
                level=Level.GREEN, message=f"Found: {astap_path}",
            ),
            ReadinessItem(
                key="astap_catalog", label="ASTAP star catalog",
                level=Level.GREEN if catalog else Level.RED,
                message=f"Found: {catalog}" if catalog else "No star catalog (.290) found",
                repair=(
                    None if catalog else
                    f"Download the H18 or D50 catalog into {astap_path.parent} "
                    f"or set astap.catalog_dir in config.toml."
                ),
            ),
        ]

    def _check_camera(self) -> ReadinessItem:
        from .. import config
        specs = {r: s for r, s in config.CAMERA_SPECS.items() if s.enabled}
        if specs:
            roles = ", ".join(
                f"{r} ({s.model or ('index ' + str(s.index))})"
                for r, s in specs.items()
            )
            return ReadinessItem(
                key="camera", label="Camera",
                level=Level.GREEN, message=f"Configured: {roles}",
            )
        return ReadinessItem(
            key="camera", label="Camera",
            level=Level.YELLOW,
            message="No camera configured — using mock (no real imaging)",
            repair='Add a [cameras.main] section to config.toml with model = "ATR585M", backend = "native"',
        )

    def _check_mount_focuser(self) -> list[ReadinessItem]:
        from .. import config
        onstep_port = os.environ.get("ONSTEP_PORT") or config.ONSTEP_PORT

        if not onstep_port:
            return [
                ReadinessItem(
                    key="mount", label="Mount (OnStep)",
                    level=Level.YELLOW,
                    message="Not configured — using mock (no real mount control)",
                    repair="Set hardware.onstep_port in config.toml, e.g.  onstep_port = '/dev/ttyUSB0'",
                ),
                ReadinessItem(
                    key="focuser", label="Focuser",
                    level=Level.YELLOW,
                    message="Not configured — autofocus disabled",
                    repair="Connect OnStep with focuser hardware.",
                ),
            ]

        # Port is configured — peek at runtime state without forcing a connection
        try:
            from ..runtime import get_runtime
            rt = get_runtime()
            if rt._adapters_built and rt._mount is not None:
                from ..ports.mount import MountState
                try:
                    import importlib.metadata
                    adapter_ver = f"v{importlib.metadata.version('onstep_adapter')}"
                except Exception:
                    try:
                        from ..adapters.onstep import __version__ as _av
                        adapter_ver = f"v{_av}"
                    except Exception:
                        adapter_ver = "?"
                state = rt._mount.get_state()
                mount_ok = state != MountState.UNKNOWN
                focuser_available = rt._focuser is not None and rt._focuser.is_available
                return [
                    ReadinessItem(
                        key="mount", label="Mount (OnStep)",
                        level=Level.GREEN if mount_ok else Level.RED,
                        message=(
                            f"Connected (adapter {adapter_ver}) — state: {state.name}"
                            if mount_ok else "Connected but state unknown"
                        ),
                        repair=None if mount_ok else "Check OnStep serial connection and retry.",
                    ),
                    ReadinessItem(
                        key="focuser", label="Focuser",
                        level=Level.GREEN if focuser_available else Level.YELLOW,
                        message="Active" if focuser_available else "Not found — autofocus disabled",
                        repair=None if focuser_available else "Check OnStep focuser wiring and configuration.",
                    ),
                ]
        except Exception:
            pass

        return [
            ReadinessItem(
                key="mount", label="Mount (OnStep)",
                level=Level.YELLOW,
                message=f"Configured on {onstep_port} — not yet connected",
                repair="Press 'Connect All' to establish connection.",
            ),
            ReadinessItem(
                key="focuser", label="Focuser",
                level=Level.YELLOW,
                message="Not yet connected",
                repair="Press 'Connect All' to establish connection.",
            ),
        ]

    def _check_unconfigured_cameras(self) -> ReadinessItem | None:
        """Return YELLOW item when cameras are connected but not in config.toml."""
        try:
            import toupcam
            from .. import config

            devices = list(toupcam.Toupcam.EnumV2())
            if not devices:
                return None

            specs = list(config.CAMERA_SPECS.values())
            configured_indices: set[int] = {
                v for v in config.CAMERAS.values() if isinstance(v, int)
            }

            unconfigured: list[str] = []
            for i, dev in enumerate(devices):
                model_name = str(dev.model.name)
                cam_id = str(dev.id)
                matched = (
                    i in configured_indices
                    or any(
                        (s.model and s.model.lower() in model_name.lower())
                        or (s.camera_id and s.camera_id == cam_id)
                        for s in specs
                    )
                )
                if not matched:
                    unconfigured.append(str(dev.displayname))

            if not unconfigured:
                return None

            names = ", ".join(unconfigured)
            n = len(unconfigured)
            return ReadinessItem(
                key="unconfigured_cameras",
                label="Unconfigured cameras",
                level=Level.YELLOW,
                message=f"{n} camera{'s' if n != 1 else ''} connected but not in config: {names}",
                repair=(
                    "See Setup & Diagnostics → Camera Scan for a suggested config snippet "
                    "to add to ~/.SmartTScope/config.toml."
                ),
            )
        except Exception:
            return None
