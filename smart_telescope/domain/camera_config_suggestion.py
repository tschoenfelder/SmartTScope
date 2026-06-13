"""Camera config suggestion — generate TOML snippets for unconfigured cameras.

Pure domain module: no I/O, no FastAPI, no SDK imports.
"""
from __future__ import annotations

ROLE_PRIORITY = ["main", "guide", "oag"]


def suggest_role(model_name: str, existing_roles: set[str]) -> str:
    """Return the most appropriate role name for an unconfigured camera.

    Walks ROLE_PRIORITY first; falls back to camera2, camera3, … when all
    standard roles are already taken.
    """
    for role in ROLE_PRIORITY:
        if role not in existing_roles:
            return role
    n = 2
    while f"camera{n}" in existing_roles:
        n += 1
    return f"camera{n}"


def _default_offset(model_name: str) -> int:
    """Return a safe default black-level offset for the camera model.

    GPCMOS guide cameras have a much lower native offset than imaging sensors.
    """
    if "GPCMOS" in model_name.upper():
        return 10
    return 150


def _default_capture_mode(has_mono: bool, has_tec: bool) -> str:
    """Monochrome TEC cameras are typically main imaging cameras; suggest streaming."""
    if has_mono and has_tec:
        return "indi-stream-trigger"
    return "snap"


def generate_toml_snippet(
    model_name: str,
    cam_id: str,
    has_tec: bool,
    has_mono: bool,
    suggested_role: str,
    first_telescope: str | None,
) -> str:
    """Return a TOML config snippet ready to append to config.toml.

    Includes a [cameras.<role>] table and a matching [optical_trains.<role>]
    table with inline guidance comments.
    """
    offset = _default_offset(model_name)
    capture_mode = _default_capture_mode(has_mono, has_tec)
    telescope = first_telescope or "c8"
    focuser = "onstep" if (has_mono and has_tec) else ""
    setup_profile = "indi" if capture_mode == "indi-stream-trigger" else "default"

    lines = [
        f"# Newly detected camera: {model_name}",
        f"# Append the following to ~/.SmartTScope/config.toml",
        "",
        f"[cameras.{suggested_role}]",
        f'model        = "{model_name}"',
        f'backend      = "native"',
        f'camera_id    = "{cam_id}"',
        f'capture_mode = "{capture_mode}"',
    ]
    if setup_profile != "default":
        lines.append(f'setup_profile = "{setup_profile}"')
    lines += [
        f"gain         = 101",
        f"offset_lcg   = {offset}   # run bias estimation wizard to calibrate",
        f"offset_hcg   = {offset}",
        f"bit_depth    = 16",
        "",
        f"[optical_trains.{suggested_role}]",
        f'telescope      = "{telescope}"   # replace with your telescope name from [telescopes]',
        f'camera         = "{suggested_role}"',
        f"reducer_factor = 1.0",
        f'focuser        = "{focuser}"   # set to "onstep" if this train uses the OnStep focuser',
    ]
    return "\n".join(lines)
