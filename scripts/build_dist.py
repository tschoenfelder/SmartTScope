#!/usr/bin/env python3
"""Build agent for smart-telescope.

Generates requirements.txt from runtime dependencies declared in
pyproject.toml, then builds a wheel into dist/.

Usage:
    python scripts/build_dist.py            # wheel only
    python scripts/build_dist.py --sdist    # wheel + source distribution
    python scripts/build_dist.py --check    # dry-run: show what would be built
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"
DIST = ROOT / "dist"


# ── helpers ───────────────────────────────────────────────────────────────────


def _load_pyproject() -> dict:  # type: ignore[type-arg]
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def _write_requirements(deps: list[str]) -> None:
    REQUIREMENTS.write_text("\n".join(deps) + "\n", encoding="utf-8")
    print(f"  requirements.txt  ({len(deps)} runtime packages)")
    for dep in deps:
        print(f"    {dep}")


def _ensure_build() -> None:
    try:
        import build  # noqa: F401
    except ModuleNotFoundError:
        print("  build package not found — installing…")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "build>=1.0"],
            stdout=subprocess.DEVNULL,
        )
        print("  build installed")


def _run_build(*, include_sdist: bool) -> list[Path]:
    cmd = [sys.executable, "-m", "build"]
    if not include_sdist:
        cmd.append("--wheel")
    cmd.append(str(ROOT))

    print(f"  running: {' '.join(cmd[2:])}")
    subprocess.check_call(cmd)

    artifacts: list[Path] = sorted(DIST.glob("*.whl"))
    if include_sdist:
        artifacts += sorted(DIST.glob("*.tar.gz"))
    return artifacts


def _latest_wheel() -> Path | None:
    wheels = sorted(DIST.glob("*.whl"))
    return wheels[-1] if wheels else None


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sdist", action="store_true", help="also build a source distribution")
    parser.add_argument("--check", action="store_true", help="dry-run: show plan without building")
    args = parser.parse_args()

    config = _load_pyproject()
    project = config["project"]
    name = project["name"]
    version = project["version"]
    deps: list[str] = project.get("dependencies", [])

    print(f"\nsmartTScope build agent — {name} {version}")
    print("=" * 50)

    if args.check:
        print("\n[dry-run] would write requirements.txt:")
        for dep in deps:
            print(f"  {dep}")
        print(f"\n[dry-run] would build wheel to {DIST}/")
        if args.sdist:
            print("[dry-run] would also build source distribution")
        wheel = _latest_wheel()
        if wheel:
            print(f"\n[existing] {wheel.name}")
        return

    print("\n1. Writing requirements.txt …")
    _write_requirements(deps)

    print("\n2. Ensuring build tool is available …")
    _ensure_build()

    print("\n3. Building …")
    artifacts = _run_build(include_sdist=args.sdist)

    print("\n" + "=" * 50)
    print("Done. Artifacts:\n")
    for artifact in artifacts:
        print(f"  {artifact}")

    wheel = _latest_wheel()
    if wheel:
        print(f"\nInstall on target machine:\n  pip install {wheel.name}")
        print(f"\nOr copy the wheel and run:\n  pip install /path/to/{wheel.name}")


if __name__ == "__main__":
    main()
