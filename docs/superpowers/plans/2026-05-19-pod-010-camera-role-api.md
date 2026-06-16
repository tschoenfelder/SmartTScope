# POD-010 Camera Role API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept `camera_role` alongside `camera_index` in the solver, calibration, and histogram endpoints so the frontend can pass the optical train role name directly, removing the client-side `_trainCamIdx()` indirection from product UI code.

**Architecture:** A new `resolve_camera_index(camera_index, camera_role)` helper in `api/deps.py` centralises role→index resolution. Each affected endpoint (solver/solve, calibration/bias|dark|flat|bpm|match, histogram/analyze) adds an optional `camera_role` field; if provided, it takes precedence over `camera_index`. The frontend (`setup.js`, `session.js`, `preview.js`) stops resolving role→index client-side for these calls and sends the role string directly. The setup-check solver call (which iterates raw SDK indices from a camera scan) is left as-is — that is an explicit diagnostic use case, acceptable per POD-004 decision. POD-009 is closed as done since M6-001..006 already define all concrete performance targets.

**Tech Stack:** Python 3.13 / FastAPI / Pydantic (backend), pytest (tests), vanilla JS (frontend).

---

## File Map

| File | Change |
|------|--------|
| `smart_telescope/api/deps.py` | Add `HTTPException` import; add `resolve_camera_index()` helper |
| `smart_telescope/api/solver.py` | Add `camera_role` to `SolveRequest`; use helper in endpoint |
| `smart_telescope/api/calibration.py` | Add `camera_role` to `BiasRequest`, `DarkRequest`, `FlatRequest`, `BpmRequest`; add `camera_role` Query param to `get_calibration_match`; use helper throughout |
| `smart_telescope/api/histogram.py` | Add `camera_role` optional Query param; use helper |
| `smart_telescope/static/js/setup.js` | Update `_calSharedParams()` + 6 call sites to use `camera_role` |
| `smart_telescope/static/js/session.js` | Update `solveFrame()` to use `camera_role` |
| `smart_telescope/static/js/preview.js` | Update `_fetchAndDrawHistogram()` to use `camera_role` |
| `tests/unit/api/test_camera_role_resolution.py` | New test file: helper + 3 endpoint acceptance tests |
| `docs/todo.md` | Mark POD-004, POD-009, POD-010 done |
| `wiki/log.md` | Append log entry |

---

### Task 1: Add `resolve_camera_index` helper to `api/deps.py`

**Files:**
- Modify: `smart_telescope/api/deps.py`
- Create: `tests/unit/api/test_camera_role_resolution.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/api/test_camera_role_resolution.py`:

```python
"""Tests for POD-010: resolve_camera_index helper in api/deps.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from smart_telescope.api import deps
from smart_telescope.api.deps import resolve_camera_index


def _mock_registry(role: str | None, camera_index: int | None) -> MagicMock:
    """Return a mock OpticalTrainRegistry where `role` resolves to camera_index (or None)."""
    reg = MagicMock()
    if camera_index is not None:
        train = MagicMock()
        train.camera_index = camera_index
        reg.by_camera_role.return_value = train
    else:
        reg.by_camera_role.return_value = None
    return reg


class TestResolveCameraIndex:
    def test_no_role_returns_camera_index_unchanged(self) -> None:
        assert resolve_camera_index(3, None) == 3

    def test_empty_string_role_returns_camera_index_unchanged(self) -> None:
        assert resolve_camera_index(2, "") == 2

    def test_valid_role_returns_train_camera_index(self) -> None:
        reg = _mock_registry("main", camera_index=1)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            result = resolve_camera_index(0, "main")
        assert result == 1

    def test_valid_role_overrides_camera_index(self) -> None:
        reg = _mock_registry("guide", camera_index=2)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            result = resolve_camera_index(99, "guide")
        assert result == 2

    def test_unknown_role_raises_422(self) -> None:
        reg = _mock_registry("nonexistent", camera_index=None)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            with pytest.raises(HTTPException) as exc_info:
                resolve_camera_index(0, "nonexistent")
        assert exc_info.value.status_code == 422
        assert "nonexistent" in exc_info.value.detail
```

- [ ] **Step 2: Run the tests to confirm they fail**

```
cd C:\Users\tscho\Documents\Torsten\TSBrain
python -m pytest tests/unit/api/test_camera_role_resolution.py -v
```

Expected: FAIL — `ImportError: cannot import name 'resolve_camera_index' from 'smart_telescope.api.deps'`.

- [ ] **Step 3: Add `resolve_camera_index` to `api/deps.py`**

In `smart_telescope/api/deps.py`, add `HTTPException` to the imports at the top of the file. Find:
```python
from __future__ import annotations

from ..ports.camera import CameraPort
```
Replace with:
```python
from __future__ import annotations

from fastapi import HTTPException

from ..ports.camera import CameraPort
```

Then add the new function at the bottom of `deps.py` (after the `reset()` function):

```python
def resolve_camera_index(camera_index: int, camera_role: str | None) -> int:
    """Resolve camera_role → camera_index when role is provided; otherwise pass camera_index through.

    Raises HTTPException 422 if camera_role is provided but not found in the registry.
    """
    if not camera_role:
        return camera_index
    registry = get_optical_train_registry()
    train = registry.by_camera_role(camera_role)
    if train is None:
        raise HTTPException(
            status_code=422,
            detail=f"camera_role {camera_role!r} not found in optical train registry",
        )
    return train.camera_index
```

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest tests/unit/api/test_camera_role_resolution.py -v
```

Expected: 5/5 PASS.

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/api/deps.py tests/unit/api/test_camera_role_resolution.py
git commit -m "feat: POD-010 — resolve_camera_index helper in api/deps"
```

---

### Task 2: Update solver, calibration, and histogram endpoints

**Files:**
- Modify: `smart_telescope/api/solver.py`
- Modify: `smart_telescope/api/calibration.py`
- Modify: `smart_telescope/api/histogram.py`
- Modify: `tests/unit/api/test_camera_role_resolution.py`

- [ ] **Step 1: Write the failing endpoint tests**

Append to `tests/unit/api/test_camera_role_resolution.py`:

```python
import numpy as np
from astropy.io import fits
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.solver import SolveResult, SolverPort

client = TestClient(app)

_solver_patches: list = []


def _mock_camera() -> MagicMock:
    cam = MagicMock(spec=CameraPort)
    rng = np.random.default_rng(0)
    pixels = rng.random((32, 32)).astype(np.float32)
    hdr = fits.Header()
    hdr["EXPTIME"] = 1.0
    cam.capture.return_value = FitsFrame(pixels=pixels, header=hdr, exposure_seconds=1.0)
    return cam


def _mock_solver_obj() -> MagicMock:
    s = MagicMock(spec=SolverPort)
    s.solve.return_value = SolveResult(success=True, ra=5.5, dec=-5.4, pa=0.0)
    return s


def _inject_solver(camera: MagicMock, solver: MagicMock) -> None:
    """Inject solver via dependency override; camera via module-level patch
    (solver.py imports get_preview_camera directly, not via deps.*)."""
    app.dependency_overrides[deps.get_solver] = lambda: solver
    p = patch("smart_telescope.api.solver.get_preview_camera", return_value=camera)
    p.start()
    _solver_patches.append(p)


@pytest.fixture(autouse=True)
def _reset_overrides() -> None:  # type: ignore[misc]
    yield
    app.dependency_overrides.clear()
    for p in _solver_patches:
        p.stop()
    _solver_patches.clear()


class TestSolverAcceptsCameraRole:
    def test_camera_role_accepted_returns_200(self) -> None:
        reg = _mock_registry("main", camera_index=0)
        _inject_solver(_mock_camera(), _mock_solver_obj())
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/solver/solve", json={"camera_role": "main", "exposure": 2.0, "gain": 200})
        assert r.status_code == 200

    def test_unknown_camera_role_returns_422(self) -> None:
        reg = _mock_registry("nope", camera_index=None)
        _inject_solver(_mock_camera(), _mock_solver_obj())
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/solver/solve", json={"camera_role": "nope", "exposure": 2.0, "gain": 200})
        assert r.status_code == 422

    def test_no_camera_role_falls_back_to_camera_index(self) -> None:
        _inject_solver(_mock_camera(), _mock_solver_obj())
        r = client.post("/api/solver/solve", json={"camera_index": 0, "exposure": 2.0, "gain": 200})
        assert r.status_code == 200


class TestHistogramAcceptsCameraRole:
    # histogram.py calls deps.get_preview_camera(...) — patch.object on deps works here
    def test_camera_role_accepted_returns_200(self) -> None:
        reg = _mock_registry("main", camera_index=0)
        with (
            patch.object(deps, "get_optical_train_registry", return_value=reg),
            patch.object(deps, "get_preview_camera", return_value=_mock_camera()),
        ):
            r = client.post("/api/histogram/analyze", params={
                "camera_role": "main", "exposure": 2.0, "gain": 200,
            })
        assert r.status_code == 200

    def test_unknown_camera_role_returns_422(self) -> None:
        reg = _mock_registry("nope", camera_index=None)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/histogram/analyze", params={
                "camera_role": "nope", "exposure": 2.0, "gain": 200,
            })
        assert r.status_code == 422

    def test_no_camera_role_falls_back_to_camera_index(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = client.post("/api/histogram/analyze", params={
                "camera_index": 0, "exposure": 2.0, "gain": 200,
            })
        assert r.status_code == 200
```

- [ ] **Step 2: Run the tests to confirm the key tests fail**

```
python -m pytest tests/unit/api/test_camera_role_resolution.py::TestSolverAcceptsCameraRole::test_unknown_camera_role_returns_422 tests/unit/api/test_camera_role_resolution.py::TestHistogramAcceptsCameraRole::test_unknown_camera_role_returns_422 -v
```

Expected: FAIL — both return 200 (camera_role is currently an unknown field and silently ignored), but tests expect 422. The other tests (valid role and no role) may trivially pass before implementation since the role is also silently ignored and the fallback `camera_index=0` is used.

- [ ] **Step 3: Update `api/solver.py`**

In `smart_telescope/api/solver.py`, find the import line:
```python
from .deps import get_preview_camera, get_solver
```
Replace with:
```python
from .deps import get_preview_camera, get_solver, resolve_camera_index
```

Find the `SolveRequest` model:
```python
class SolveRequest(BaseModel):
    exposure:     float = Field(default=5.0, gt=0.0, le=60.0)
    gain:         int   = Field(default=100, ge=100, le=3200)
    camera_index: int   = Field(default=0, ge=0, le=7)
    pixel_scale:  float | None = Field(default=None, gt=0.0)
```
Replace with:
```python
class SolveRequest(BaseModel):
    exposure:     float = Field(default=5.0, gt=0.0, le=60.0)
    gain:         int   = Field(default=100, ge=100, le=3200)
    camera_index: int   = Field(default=0, ge=0, le=7)
    camera_role:  str | None = Field(default=None)
    pixel_scale:  float | None = Field(default=None, gt=0.0)
```

In the `solver_solve` endpoint, find:
```python
    camera = get_preview_camera(body.camera_index)
```
Replace with:
```python
    camera = get_preview_camera(resolve_camera_index(body.camera_index, body.camera_role))
```

- [ ] **Step 4: Update `api/histogram.py`**

In `smart_telescope/api/histogram.py`, update the `analyze_histogram` signature. Find:
```python
async def analyze_histogram(
    camera_index: int = Query(default=0, ge=0, le=7),
    exposure: float = Query(default=2.0, gt=0.0, le=60.0),
    gain: int = Query(default=100, ge=0),
    bit_depth: int = Query(default=12, ge=8, le=16),
    n_bins: int = Query(default=512, ge=64, le=4096),
) -> HistogramResponse:
```
Replace with:
```python
async def analyze_histogram(
    camera_index: int = Query(default=0, ge=0, le=7),
    camera_role: str | None = Query(default=None),
    exposure: float = Query(default=2.0, gt=0.0, le=60.0),
    gain: int = Query(default=100, ge=0),
    bit_depth: int = Query(default=12, ge=8, le=16),
    n_bins: int = Query(default=512, ge=64, le=4096),
) -> HistogramResponse:
```

Then in the endpoint body, find:
```python
    try:
        camera = deps.get_preview_camera(camera_index)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
```
Replace with:
```python
    try:
        camera = deps.get_preview_camera(deps.resolve_camera_index(camera_index, camera_role))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
```

- [ ] **Step 5: Run the endpoint tests to verify they pass**

```
python -m pytest tests/unit/api/test_camera_role_resolution.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 6: Update `api/calibration.py`**

**6a — Add `camera_role` to request models.**

Find `BiasRequest`:
```python
class BiasRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    n_frames: int = Field(default=32, ge=1, le=200)
    gain: int | None = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")
```
Replace with:
```python
class BiasRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    camera_role:  str | None = Field(default=None)
    n_frames: int = Field(default=32, ge=1, le=200)
    gain: int | None = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")
```

Find `DarkRequest`:
```python
class DarkRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    exposure_ms: float = Field(ge=1.0, le=3_600_000.0, description="Dark exposure in milliseconds")
    n_frames: int = Field(default=20, ge=1, le=200)
    gain: int | None = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")
```
Replace with:
```python
class DarkRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    camera_role:  str | None = Field(default=None)
    exposure_ms: float = Field(ge=1.0, le=3_600_000.0, description="Dark exposure in milliseconds")
    n_frames: int = Field(default=20, ge=1, le=200)
    gain: int | None = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")
```

Find `FlatRequest`:
```python
class FlatRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    optical_train: str = Field(min_length=1, max_length=64, description="Optical train profile ID")
    filter_id: str = Field(default="none", max_length=32, description="Filter identifier or 'none'")
    n_frames: int = Field(default=15, ge=1, le=200)
    initial_exposure_s: float = Field(default=1.0, ge=0.001, le=3600.0,
                                      description="Starting exposure for auto-tune")
    gain: int | None = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")
```
Replace with:
```python
class FlatRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    camera_role:  str | None = Field(default=None)
    optical_train: str = Field(min_length=1, max_length=64, description="Optical train profile ID")
    filter_id: str = Field(default="none", max_length=32, description="Filter identifier or 'none'")
    n_frames: int = Field(default=15, ge=1, le=200)
    initial_exposure_s: float = Field(default=1.0, ge=0.001, le=3600.0,
                                      description="Starting exposure for auto-tune")
    gain: int | None = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")
```

Find `BpmRequest`:
```python
class BpmRequest(BaseModel):
    camera_index: int  = Field(default=0, ge=0, le=7)
    n_frames: int      = Field(default=20, ge=5, le=200)
    gain: int | None   = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")
    hot_sigma: float   = Field(default=5.0, ge=1.0, le=20.0)
    dead_sigma: float  = Field(default=5.0, ge=1.0, le=20.0)
    noisy_factor: float = Field(default=3.0, ge=1.0, le=10.0)
```
Replace with:
```python
class BpmRequest(BaseModel):
    camera_index: int  = Field(default=0, ge=0, le=7)
    camera_role:  str | None = Field(default=None)
    n_frames: int      = Field(default=20, ge=5, le=200)
    gain: int | None   = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")
    hot_sigma: float   = Field(default=5.0, ge=1.0, le=20.0)
    dead_sigma: float  = Field(default=5.0, ge=1.0, le=20.0)
    noisy_factor: float = Field(default=3.0, ge=1.0, le=10.0)
```

**6b — Use `resolve_camera_index` in each endpoint handler.**

In `start_bias()`, find:
```python
    camera = _get_camera(req.camera_index)
```
Replace with (all four: bias, dark, flat, bpm — find each occurrence separately):
```python
    camera = _get_camera(deps.resolve_camera_index(req.camera_index, req.camera_role))
```

There are 4 such lines to change (lines ~164, ~207, ~253, ~342 — one per endpoint). Change each one.

**6c — Add `camera_role` Query param to `get_calibration_match`.**

In the `get_calibration_match` function signature, find:
```python
def get_calibration_match(
    camera_index: int   = Query(default=0, ge=0, le=7),
    gain: int           = Query(ge=0, le=5000),
```
Replace with:
```python
def get_calibration_match(
    camera_index: int   = Query(default=0, ge=0, le=7),
    camera_role: str | None = Query(default=None),
    gain: int           = Query(ge=0, le=5000),
```

Then in the function body, find:
```python
    camera = _get_camera(camera_index)
```
Replace with:
```python
    camera = _get_camera(deps.resolve_camera_index(camera_index, camera_role))
```

- [ ] **Step 7: Run the full test suite to catch regressions**

```
python -m pytest tests/unit/api/test_camera_role_resolution.py tests/unit/api/test_calibration.py tests/unit/api/test_solver.py tests/unit/api/test_histogram.py -v
```

Expected: all pass (original tests plus the 11 new ones).

- [ ] **Step 8: Commit**

```bash
git add smart_telescope/api/solver.py smart_telescope/api/calibration.py smart_telescope/api/histogram.py tests/unit/api/test_camera_role_resolution.py
git commit -m "feat: POD-010 — accept camera_role in solver, calibration, histogram endpoints"
```

---

### Task 3: Update frontend to use `camera_role` directly

**Files:**
- Modify: `smart_telescope/static/js/setup.js`
- Modify: `smart_telescope/static/js/session.js`
- Modify: `smart_telescope/static/js/preview.js`

No new tests — the smoke tests cover HTML/API loading; backend endpoint tests cover role resolution.

- [ ] **Step 1: Update `setup.js` — `_calSharedParams()` and all 6 calibration/histogram callers**

**Change 1 — `_calSharedParams()`**: Find:
```javascript
function _calSharedParams() {
    return {
      camIdx : _trainCamIdx(document.getElementById('preview-cam-select')?.value || 'main'),
      gain   : parseInt(document.getElementById('s4-cal-gain').value,    10) || 100,
      offset : parseInt(document.getElementById('s4-cal-offset').value,  10) || 0,
    };
}
```
Replace with:
```javascript
function _calSharedParams() {
    return {
      camRole: document.getElementById('preview-cam-select')?.value || 'main',
      gain   : parseInt(document.getElementById('s4-cal-gain').value,    10) || 100,
      offset : parseInt(document.getElementById('s4-cal-offset').value,  10) || 0,
    };
}
```

**Change 2 — `prepareBias()`**: Find:
```javascript
    const { camIdx, gain, offset } = _calSharedParams();
    const nFrames = parseInt(document.getElementById('s4-bias-nframes').value, 10) || 32;
    try {
      const { job_id } = await apiPost('/api/calibration/bias',
        { camera_index: camIdx, n_frames: nFrames, gain, offset });
```
Replace with:
```javascript
    const { camRole, gain, offset } = _calSharedParams();
    const nFrames = parseInt(document.getElementById('s4-bias-nframes').value, 10) || 32;
    try {
      const { job_id } = await apiPost('/api/calibration/bias',
        { camera_role: camRole, n_frames: nFrames, gain, offset });
```

**Change 3 — `prepareFlat()`**: Find:
```javascript
    const { camIdx, gain, offset } = _calSharedParams();
    const nFrames  = parseInt(document.getElementById('s4-flat-nframes').value,    10) || 15;
    const initExpS = parseFloat(document.getElementById('s4-flat-init-exp').value) || 1.0;
    const train    = (document.getElementById('s4-flat-train').value  || '').trim();
    const filter   = (document.getElementById('s4-flat-filter').value || 'none').trim();
    if (!train) {
      setStatus('s4-flat-status', 'Optical train profile ID is required.', true);
      btn.disabled = false; btn.innerHTML = 'Prepare'; return;
    }
    try {
      const { job_id } = await apiPost('/api/calibration/flat', {
        camera_index: camIdx, n_frames: nFrames,
```
Replace with:
```javascript
    const { camRole, gain, offset } = _calSharedParams();
    const nFrames  = parseInt(document.getElementById('s4-flat-nframes').value,    10) || 15;
    const initExpS = parseFloat(document.getElementById('s4-flat-init-exp').value) || 1.0;
    const train    = (document.getElementById('s4-flat-train').value  || '').trim();
    const filter   = (document.getElementById('s4-flat-filter').value || 'none').trim();
    if (!train) {
      setStatus('s4-flat-status', 'Optical train profile ID is required.', true);
      btn.disabled = false; btn.innerHTML = 'Prepare'; return;
    }
    try {
      const { job_id } = await apiPost('/api/calibration/flat', {
        camera_role: camRole, n_frames: nFrames,
```

**Change 4 — `prepareDark()`**: Find:
```javascript
    const { camIdx, gain, offset } = _calSharedParams();
    const nFrames   = parseInt(document.getElementById('s4-dark-nframes').value,  10) || 20;
    const expS      = parseFloat(document.getElementById('s4-dark-exp').value) || 120.0;
    const exposureMs = expS * 1000.0;
    try {
      const { job_id } = await apiPost('/api/calibration/dark',
        { camera_index: camIdx, n_frames: nFrames, exposure_ms: exposureMs, gain, offset });
```
Replace with:
```javascript
    const { camRole, gain, offset } = _calSharedParams();
    const nFrames   = parseInt(document.getElementById('s4-dark-nframes').value,  10) || 20;
    const expS      = parseFloat(document.getElementById('s4-dark-exp').value) || 120.0;
    const exposureMs = expS * 1000.0;
    try {
      const { job_id } = await apiPost('/api/calibration/dark',
        { camera_role: camRole, n_frames: nFrames, exposure_ms: exposureMs, gain, offset });
```

**Change 5 — `prepareBpm()`**: Find:
```javascript
    const { camIdx, gain, offset } = _calSharedParams();
    const nFrames = parseInt(document.getElementById('s4-bpm-nframes').value, 10) || 20;
    const sigma   = parseFloat(document.getElementById('s4-bpm-sigma').value) || 5.0;
    try {
      const { job_id } = await apiPost('/api/calibration/bpm',
        { camera_index: camIdx, n_frames: nFrames, gain, offset,
```
Replace with:
```javascript
    const { camRole, gain, offset } = _calSharedParams();
    const nFrames = parseInt(document.getElementById('s4-bpm-nframes').value, 10) || 20;
    const sigma   = parseFloat(document.getElementById('s4-bpm-sigma').value) || 5.0;
    try {
      const { job_id } = await apiPost('/api/calibration/bpm',
        { camera_role: camRole, n_frames: nFrames, gain, offset,
```

**Change 6 — `checkCalibrationMatch()`**: Find:
```javascript
    const { camIdx, gain, offset } = _calSharedParams();
    const expS      = parseFloat(document.getElementById('s4-dark-exp').value) || 120.0;
    const train     = (document.getElementById('s4-flat-train').value  || '').trim() || null;
    const filter    = (document.getElementById('s4-flat-filter').value || 'none').trim() || null;

    const params = new URLSearchParams({ gain, offset, camera_index: camIdx });
```
Replace with:
```javascript
    const { camRole, gain, offset } = _calSharedParams();
    const expS      = parseFloat(document.getElementById('s4-dark-exp').value) || 120.0;
    const train     = (document.getElementById('s4-flat-train').value  || '').trim() || null;
    const filter    = (document.getElementById('s4-flat-filter').value || 'none').trim() || null;

    const params = new URLSearchParams({ gain, offset, camera_role: camRole });
```

**Change 7 — `s5CheckCalibration()`**: Find:
```javascript
    const camIdx = _trainCamIdx(document.getElementById('preview-cam-select')?.value || 'main');
    const gain   = parseInt(document.getElementById('s4-cal-gain')?.value,  10) || 100;
    const offset = parseInt(document.getElementById('s4-cal-offset')?.value, 10) || 0;
    // Use the session exposure (science frame) for dark matching
    const expS   = parseFloat(document.getElementById('s5-exposure')?.value) || 30.0;
    // Use the session optical train profile for flat matching
    const train  = (document.getElementById('s5-profile')?.value || '').trim() || null;
    const filter = (document.getElementById('s4-flat-filter')?.value || 'none').trim() || null;

    const params = new URLSearchParams({ gain, offset, camera_index: camIdx });
```
Replace with:
```javascript
    const camRole = document.getElementById('preview-cam-select')?.value || 'main';
    const gain   = parseInt(document.getElementById('s4-cal-gain')?.value,  10) || 100;
    const offset = parseInt(document.getElementById('s4-cal-offset')?.value, 10) || 0;
    // Use the session exposure (science frame) for dark matching
    const expS   = parseFloat(document.getElementById('s5-exposure')?.value) || 30.0;
    // Use the session optical train profile for flat matching
    const train  = (document.getElementById('s5-profile')?.value || '').trim() || null;
    const filter = (document.getElementById('s4-flat-filter')?.value || 'none').trim() || null;

    const params = new URLSearchParams({ gain, offset, camera_role: camRole });
```

- [ ] **Step 2: Update `session.js` — `solveFrame()`**

In `smart_telescope/static/js/session.js`, find:
```javascript
    const camIdx   = _trainCamIdx(document.getElementById('preview-cam-select')?.value || 'main');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Solving…';
    result.style.display = 'none';
    setStatus('s3-status', '');
    try {
      const data = await apiPost('/api/solver/solve', { exposure, gain, camera_index: camIdx });
```
Replace with:
```javascript
    const camRole  = document.getElementById('preview-cam-select')?.value || 'main';
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Solving…';
    result.style.display = 'none';
    setStatus('s3-status', '');
    try {
      const data = await apiPost('/api/solver/solve', { exposure, gain, camera_role: camRole });
```

- [ ] **Step 3: Update `preview.js` — `_fetchAndDrawHistogram()`**

In `smart_telescope/static/js/preview.js`, find:
```javascript
    const camIdx   = _trainCamIdx(document.getElementById('preview-cam-select')?.value || 'main');
    const params   = new URLSearchParams({
      camera_index: camIdx, exposure, gain, bit_depth: 12, n_bins: 256,
    });
```
Replace with:
```javascript
    const camRole  = document.getElementById('preview-cam-select')?.value || 'main';
    const params   = new URLSearchParams({
      camera_role: camRole, exposure, gain, bit_depth: 12, n_bins: 256,
    });
```

- [ ] **Step 4: Run the smoke tests to verify no regressions**

```
python -m pytest tests/unit/api/test_smoke.py -v
```

Expected: all 44 pass.

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/static/js/setup.js smart_telescope/static/js/session.js smart_telescope/static/js/preview.js
git commit -m "feat: POD-010 — frontend sends camera_role directly (solver, calibration, histogram)"
```

---

### Task 4: Mark POD-004, POD-009, POD-010 done and update wiki

**Files:**
- Modify: `docs/todo.md`
- Modify: `wiki/log.md`

- [ ] **Step 1: Update `docs/todo.md`**

**Change A — POD-004:** Find:
```
- [ ] POD-004 Is SDK camera index acceptable anywhere outside diagnostics?
```
Replace with:
```
- [x] POD-004 Is SDK camera index acceptable anywhere outside diagnostics?
  - *Decision:* SDK camera index is NOT acceptable in the product UI (enforced by R4). SDK camera index IS accepted in API request bodies for backward compatibility — `camera_role` is preferred. In Stage 6 diagnostics, `sdk_index` from camera scan results is shown and used (by design).
```

**Change B — POD-009:** Find:
```
- [ ] POD-009 Concrete performance targets: preview latency, solve time, centering accuracy, Pi thermal ceiling?
```
Replace with:
```
- [x] POD-009 Concrete performance targets: preview latency, solve time, centering accuracy, Pi thermal ceiling?
  - *Decision (M6-001..006):* 6-hour unattended session; ≤2 s preview latency; ≤500 ms STOP response; ≤30 arcsec centering accuracy; ≥90% plate-solve success rate; ≤75°C Pi thermal ceiling. All targets tracked in `domain/performance_targets.py` and `GET /api/performance-targets`.
```

**Change C — POD-010:** Find:
```
- [ ] POD-010 Should SDK camera indices be forbidden in API request bodies, or only hidden in the UI? `[P2 · Process]`
  - *Context:* R4 removed indices from product UI; some API endpoints still accept index directly. Decision needed for API contract (affects R4-008 and any client tooling).
```
Replace with:
```
- [x] POD-010 Should SDK camera indices be forbidden in API request bodies, or only hidden in the UI? `[P2 · Process]`
  - *Decision:* `camera_role` is the preferred parameter for all product-facing API endpoints. `camera_index` is accepted for backward compatibility. New product UI code must use `camera_role`; diagnostic code may use `camera_index` directly.
  - *Done:* `deps.resolve_camera_index()` helper; `camera_role` added to solver/solve, calibration/bias|dark|flat|bpm|match, histogram/analyze; frontend setup.js/session.js/preview.js updated to send `camera_role` directly; 11 new tests in `TestResolveCameraIndex`, `TestSolverAcceptsCameraRole`, `TestHistogramAcceptsCameraRole`.
```

Also update the **Last updated** line. Find:
```
**Last updated:** 2026-05-19 (BUG-002 autogain layout; R7-006 evidence-gap report; M6-001–006 performance targets; M6-012 release notes; POD-005 isolation policy; M5-001/003/004 guided startup)
```
Replace with:
```
**Last updated:** 2026-05-19 (BUG-002 autogain layout; R7-006 evidence-gap report; M6-001–006 performance targets; M6-012 release notes; POD-005 isolation policy; M5-001/003/004 guided startup; POD-004/009/010 camera role API)
```

- [ ] **Step 2: Prepend log entry to `wiki/log.md`**

Add immediately after the opening `---` separator (before the first existing `## ` entry):

```markdown
## 2026-05-19 — POD-010 — Camera role resolution in API endpoints

**What changed:**
- `smart_telescope/api/deps.py`: Added `resolve_camera_index(camera_index, camera_role)` helper — returns `camera_index` when no role given; resolves role via `OpticalTrainRegistry` when provided; raises HTTP 422 for unknown roles.
- `smart_telescope/api/solver.py`: `SolveRequest` accepts optional `camera_role`.
- `smart_telescope/api/calibration.py`: `BiasRequest`, `DarkRequest`, `FlatRequest`, `BpmRequest` accept optional `camera_role`; `GET /api/calibration/match` accepts `camera_role` Query param.
- `smart_telescope/api/histogram.py`: `POST /api/histogram/analyze` accepts `camera_role` Query param.
- `smart_telescope/static/js/setup.js`: Calibration and histogram calls now send `camera_role` directly; `_calSharedParams()` returns `camRole` instead of `camIdx`.
- `smart_telescope/static/js/session.js`: `solveFrame()` sends `camera_role` directly.
- `smart_telescope/static/js/preview.js`: `_fetchAndDrawHistogram()` sends `camera_role` directly.
- `tests/unit/api/test_camera_role_resolution.py`: 11 new tests.
- `docs/todo.md`: POD-004, POD-009, POD-010 marked done.

**Tests:** ≥2688 passed

---
```

- [ ] **Step 3: Commit**

```bash
git add docs/todo.md wiki/log.md
git commit -m "docs: POD-004/009/010 done — camera role API, performance targets, SDK index policy"
```
