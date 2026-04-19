import configparser
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ...ports.solver import SolverPort, SolveResult

# Default install path on Windows; also checked via PATH
_ASTAP_DEFAULT = Path("C:/Program Files/astap/astap.exe")


def find_astap() -> Optional[str]:
    """Return path to astap executable, or None if not found."""
    on_path = shutil.which("astap")
    if on_path:
        return on_path
    if _ASTAP_DEFAULT.exists():
        return str(_ASTAP_DEFAULT)
    return None


class AstapSolver(SolverPort):
    """
    Real plate-solver adapter wrapping the ASTAP CLI.

    ASTAP writes a .ini file alongside the input with the WCS solution.
    RA/Dec in the output are in degrees (CRVAL1, CRVAL2).
    """

    def __init__(
        self,
        astap_path: Optional[str] = None,
        search_radius_deg: float = 30.0,
        downsample: int = 0,          # 0 = auto
        timeout_seconds: int = 60,
    ) -> None:
        self._astap = astap_path or find_astap()
        if not self._astap:
            raise RuntimeError(
                "ASTAP not found. Install from https://www.hnsky.org/astap.htm "
                "or pass astap_path explicitly."
            )
        self._search_radius = search_radius_deg
        self._downsample = downsample
        self._timeout = timeout_seconds

    def solve(self, frame_data: bytes, pixel_scale_hint: float) -> SolveResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            fits_path = Path(tmpdir) / "frame.fits"
            fits_path.write_bytes(frame_data)

            cmd = [
                self._astap,
                "-f", str(fits_path),
                "-r", str(self._search_radius),
                "-z", str(self._downsample),
                "-scale", str(round(pixel_scale_hint, 4)),
                "-o", str(fits_path.with_suffix("")),   # output prefix
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                )
            except subprocess.TimeoutExpired:
                return SolveResult(success=False, error="ASTAP timed out")
            except Exception as exc:
                return SolveResult(success=False, error=f"ASTAP launch failed: {exc}")

            ini_path = fits_path.with_suffix(".ini")
            if not ini_path.exists():
                return SolveResult(
                    success=False,
                    error=f"ASTAP produced no output (exit {proc.returncode}): {proc.stderr.strip()}",
                )

            return self._parse_ini(ini_path)

    @staticmethod
    def _parse_ini(ini_path: Path) -> SolveResult:
        cfg = configparser.ConfigParser()
        cfg.read(ini_path)

        section = "Solution" if cfg.has_section("Solution") else cfg.sections()[0] if cfg.sections() else None
        if section is None:
            return SolveResult(success=False, error="ASTAP .ini has no sections")

        solved = cfg.get(section, "PLATESOLVED", fallback="F").strip().upper()
        if solved != "T":
            warning = cfg.get(section, "WARNING", fallback="").strip()
            return SolveResult(success=False, error=warning or "ASTAP: PLATESOLVED=F")

        try:
            ra_deg  = float(cfg.get(section, "CRVAL1"))   # RA in degrees
            dec_deg = float(cfg.get(section, "CRVAL2"))   # Dec in degrees
            pa      = float(cfg.get(section, "CROTA2", fallback="0"))
        except (ValueError, configparser.NoOptionError) as exc:
            return SolveResult(success=False, error=f"ASTAP .ini parse error: {exc}")

        return SolveResult(
            success=True,
            ra=ra_deg / 15.0,   # convert degrees → hours to match port contract
            dec=dec_deg,
            pa=pa,
        )
