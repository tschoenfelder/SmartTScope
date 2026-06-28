"""Optional external frame-analyzer adapter.

An external Python module may expose an analyze_frame() function with the
signature defined by FrameAnalyzerProtocol.  SmartTScope loads it lazily at
startup when EXTERNAL_FRAME_ANALYZER_MODULE is configured.

The external function is responsible for maintaining its own temporal state
(previous-frame buffers); SmartTScope simply calls it once per captured frame.

Usage::

    # In config.toml [analysis] section:
    external_frame_analyzer_module = "my_star_counter"

    # Runtime wires it via:
    rt.frame_analyzer = load_external_analyzer(config.EXTERNAL_FRAME_ANALYZER_MODULE)

    # Services call it as:
    if rt.frame_analyzer is not None:
        result = rt.frame_analyzer.analyze_frame(pixels, exposure_s=..., gain=..., offset=...)
"""
from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

import numpy as np

from ..domain.star_count import StarCountResult

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)


@runtime_checkable
class FrameAnalyzerProtocol(Protocol):
    """Structural interface for a frame analyzer compatible with SmartTScope."""

    def analyze_frame(
        self,
        image: np.ndarray,
        *,
        exposure_s: float | None,
        gain: int | None,
        offset: int | None,
    ) -> StarCountResult:
        """Analyze one image frame and return star counts and capture suggestions."""
        ...


class ExternalFrameAnalyzer:
    """Adapter that wraps an external module-level analyze_frame() function.

    The external function signature must match exactly::

        def analyze_frame(
            image: np.ndarray,
            *,
            exposure_s: float | None,
            gain: int | None,
            offset: int | None,
        ) -> StarCountResult: ...

    The external function is responsible for maintaining its own temporal
    state (e.g. previous-frame buffers for improved star-position estimation).
    This adapter is stateless — it simply bridges the module-level function
    to the Protocol's instance-method convention.
    """

    def __init__(self, fn: Callable[..., StarCountResult], module_name: str) -> None:
        self._fn = fn
        self._module_name = module_name

    def analyze_frame(
        self,
        image: np.ndarray,
        *,
        exposure_s: float | None,
        gain: int | None,
        offset: int | None,
    ) -> StarCountResult:
        return self._fn(image, exposure_s=exposure_s, gain=gain, offset=offset)

    def __repr__(self) -> str:
        return f"ExternalFrameAnalyzer(module={self._module_name!r})"


def load_external_analyzer(module_name: str) -> FrameAnalyzerProtocol | None:
    """Import *module_name* and return an ExternalFrameAnalyzer wrapping its
    analyze_frame() function.

    Returns None (and logs a warning) when:
    - module_name is empty or None
    - the module cannot be imported (ImportError)
    - the module has no analyze_frame attribute (AttributeError)
    """
    if not module_name:
        return None

    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        _log.warning(
            "ExternalFrameAnalyzer: module %r not available (%s) — "
            "built-in analysis only",
            module_name, exc,
        )
        return None

    fn = getattr(mod, "analyze_frame", None)
    if fn is None or not callable(fn):
        _log.warning(
            "ExternalFrameAnalyzer: module %r has no callable analyze_frame() — "
            "built-in analysis only",
            module_name,
        )
        return None

    analyzer = ExternalFrameAnalyzer(fn, module_name)
    _log.info("ExternalFrameAnalyzer: loaded from %r", module_name)
    return analyzer
