import configparser
import shutil
import subprocess
import tempfile
from pathlib import Path

from ...domain.frame import FitsFrame
from ...ports.solver import SolveResult, SolverPort

_ASTAP_DEFAULT = Path("C:/Program Files/astap/astap.exe")

_CATALOG_SEARCH_DIRS: list[Path] = [
    Path.home() / ".astap",
    Path("/usr/share/astap"),
    Path("/usr/local/share/astap"),
    Path("/var/lib/astap"),
    Path("/opt/astap"),
    Path("C:/ProgramData/astap"),
]


def find_astap() -> str | None:
    """Return path to astap executable, or None if not found."""
    on_path = shutil.which("astap")
    if on_path:
        return on_path
    if _ASTAP_DEFAULT.exists():
        return str(_ASTAP_DEFAULT)
    return None


def find_catalog(
    astap_exe: str | None = None,
    catalog_dir: str | None = None,
) -> Path | None:
    """Return directory containing an ASTAP star catalog (.290 files), or None.

    Works with all catalog families: D05, D20, D50, D80 (and legacy G17).
    *catalog_dir* is checked first when provided (from config file).
    """
    search: list[Path] = []
    if catalog_dir:
        search.append(Path(catalog_dir))
    if astap_exe:
        search.append(Path(astap_exe).parent)
    search.extend(_CATALOG_SEARCH_DIRS)
    for d in search:
        if d.is_dir() and any(d.glob("*.290")):
            return d
    return None


def catalog_search_paths(astap_exe: str | None = None, catalog_dir: str | None = None) -> list[str]:
    """Return the list of paths that would be searched by find_catalog()."""
    paths: list[Path] = []
    if catalog_dir:
        paths.append(Path(catalog_dir))
    if astap_exe:
        paths.append(Path(astap_exe).parent)
    paths.extend(_CATALOG_SEARCH_DIRS)
    return [str(p) for p in paths]


# Backward-compatible alias.
find_g17_catalog = find_catalog


class AstapSolver(SolverPort):
    """
    Real plate-solver adapter wrapping the ASTAP CLI.

    ASTAP writes a .ini file alongside the input with the WCS solution.
    RA/Dec in the output are in degrees (CRVAL1, CRVAL2).
    """

    def __init__(
        self,
        astap_path: str | None = None,
        catalog_dir: str | None = None,
        search_radius_deg: float = 30.0,
        downsample: int = 0,
        timeout_seconds: int = 60,
    ) -> None:
        resolved = astap_path or find_astap()
        if not resolved:
            raise RuntimeError(
                "ASTAP not found. Install from https://www.hnsky.org/astap.htm "
                "or pass astap_path explicitly."
            )
        self._astap: str = resolved
        self._catalog_dir = catalog_dir
        self._search_radius = search_radius_deg
        self._downsample = downsample
        self._timeout = timeout_seconds

    def solve(
        self,
        frame: FitsFrame,
        pixel_scale_hint: float,
        search_radius_deg: float | None = None,
    ) -> SolveResult:
        radius = search_radius_deg if search_radius_deg is not None else self._search_radius
        with tempfile.TemporaryDirectory() as tmpdir:
            fits_path = Path(tmpdir) / "frame.fits"
            fits_path.write_bytes(frame.to_fits_bytes())

            cmd: list[str] = [
                self._astap,
                "-f", str(fits_path),
                "-r", str(radius),
                "-z", str(self._downsample),
                "-scale", str(round(pixel_scale_hint, 4)),
                "-o", str(fits_path.with_suffix("")),
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
                    error=(
                        f"ASTAP produced no output (exit {proc.returncode}): "
                        f"{proc.stderr.strip()}"
                    ),
                )

            return self._parse_ini(ini_path)

    @staticmethod
    def _parse_ini(ini_path: Path) -> SolveResult:
        cfg = configparser.ConfigParser()
        cfg.read(ini_path)

        section = (
            "Solution" if cfg.has_section("Solution")
            else cfg.sections()[0] if cfg.sections()
            else None
        )
        if section is None:
            return SolveResult(success=False, error="ASTAP .ini has no sections")

        solved = cfg.get(section, "PLATESOLVED", fallback="F").strip().upper()
        if solved != "T":
            warning = cfg.get(section, "WARNING", fallback="").strip()
            return SolveResult(success=False, error=warning or "ASTAP: PLATESOLVED=F")

        try:
            ra_deg = float(cfg.get(section, "CRVAL1"))
            dec_deg = float(cfg.get(section, "CRVAL2"))
            pa = float(cfg.get(section, "CROTA2", fallback="0"))
        except (ValueError, configparser.NoOptionError) as exc:
            return SolveResult(success=False, error=f"ASTAP .ini parse error: {exc}")

        return SolveResult(
            success=True,
            ra=ra_deg / 15.0,
            dec=dec_deg,
            pa=pa,
        )
