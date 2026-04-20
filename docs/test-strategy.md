# SmartTScope — Test Strategy

**Author**: External Agile Coach
**Date**: 2026-04-21
**Companion files**: `tests/conftest.py`, `tests/unit/workflow/test_runner_stages.py`

---

## The testing pyramid

The target distribution for this codebase is:

```
          /\
         /  \   10%  Hardware tests
        /----\       (real Pi 5 + telescope, skipped in CI)
       /      \
      /  20%   \  Integration tests
     /  (fakes) \  (hand-rolled fakes, full pipeline, no hardware)
    /------------\
   /             \
  /     70%       \  Unit tests
 /  (mocks + pure) \  (Mock(spec=), patch, pure functions — fast, isolated)
/___________________\
```

The current codebase inverts this. All 39 tests are in `tests/integration/` and exercise the full pipeline. That is not wrong — it caught real bugs — but it is expensive to maintain, slow to run, and gives no signal about *which component* broke when something fails.

**The goal**: 70% of tests never touch a port implementation, never run the full pipeline, and complete in milliseconds. They test one thing in isolation, with collaborators replaced by `Mock(spec=...)` objects.

---

## Why `Mock(spec=...)`, not hand-rolled fakes, for unit tests

The project already has `MockCamera`, `MockMount`, `MockSolver`, etc. These are **fakes** — simplified implementations that behave like the real thing. Fakes are the right tool for integration tests. They are the wrong tool for unit tests of individual pipeline stages, for three reasons:

**1. Fakes test the pipeline, not the stage.**
When a test using `MockCamera` fails, you know something in the 9-stage pipeline broke. You do not know which stage or why. A mock that instruments a single method call fails at the exact line that made the wrong call.

**2. Fakes drift from the interface.**
`MockMount.goto()` returns `True` by default. If `MountPort.goto()` changes its signature, `MockMount` compiles fine and the test still passes. `Mock(spec=MountPort)` raises `AttributeError` immediately if the method name changes.

**3. Fakes cannot verify interaction.**
A fake cannot tell you "was `sync()` called exactly once, with these arguments, before `goto()`?" A mock can.

### The distinction in practice

| Tool | Right use | Wrong use |
|---|---|---|
| `Mock(spec=Port)` | Unit test of a single stage; verify calls and arguments | Full pipeline test |
| Hand-rolled fake | Integration test of full pipeline; verify observable outcomes | Testing that `connect()` was called |
| `patch` | Isolate external dependency (subprocess, serial, time) | Replacing a port |
| Real adapter | Hardware test; verify contract with real device | CI |

---

## Key mock patterns

### Pattern 1 — `Mock(spec=...)` enforces the interface

```python
from unittest.mock import Mock
from smart_telescope.ports.mount import MountPort

mount = Mock(spec=MountPort)
mount.connect.return_value = True

# ✓ Calling a real method works
mount.connect()

# ✗ Typo caught immediately — not at runtime on real hardware
mount.conect()  # AttributeError: Mock object has no attribute 'conect'
```

### Pattern 2 — `side_effect` for sequences and exceptions

```python
from smart_telescope.ports.solver import SolverPort, SolveResult

solver = Mock(spec=SolverPort)

# Return different values on successive calls
solver.solve.side_effect = [
    SolveResult(success=False, error="no stars"),   # attempt 1
    SolveResult(success=True, ra=5.5881, dec=-5.391),  # attempt 2
]

# Or raise on a specific call
mount = Mock(spec=MountPort)
mount.is_slewing.side_effect = [True, True, False]  # slewing, slewing, done
```

### Pattern 3 — `call_args` and `assert_called_once_with` for interaction verification

```python
solver = Mock(spec=SolverPort)
solver.solve.return_value = SolveResult(success=True, ra=5.5881, dec=-5.391)
runner = make_runner(solver=solver, optical_profile=C8_NATIVE)
runner._stage_align(make_log())

# Verify the pixel scale hint is from the profile, not hardcoded
_, pixel_scale = solver.solve.call_args.args
assert pixel_scale == pytest.approx(0.38)

# Verify it was called exactly once
solver.solve.assert_called_once()
```

### Pattern 4 — `patch` for time, subprocess, and serial

```python
from unittest.mock import patch
import subprocess

# Patch time.sleep to keep tests instant
with patch("smart_telescope.workflow.runner.time.sleep") as mock_sleep:
    runner._wait_for_slew("goto")
assert mock_sleep.call_count == 2  # polled twice before stopping

# Patch subprocess.run to simulate ASTAP timeout
with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("astap", 60)):
    result = solver.solve(b"fits_data", 0.38)
assert not result.success
assert "timed out" in result.error
```

### Pattern 5 — `patch` for module constants

The runner's `SLEW_TIMEOUT_S = 120.0` makes the real timeout test take 2 minutes. Patch it:

```python
import smart_telescope.workflow.runner as runner_module

with patch.object(runner_module, "SLEW_TIMEOUT_S", 4.0), \
     patch.object(runner_module, "SLEW_POLL_INTERVAL_S", 2.0), \
     patch("smart_telescope.workflow.runner.time.sleep"):
    with pytest.raises(WorkflowError) as exc:
        runner._wait_for_slew("goto")
assert "timed out" in exc.value.reason.lower()
```

### Pattern 6 — `AsyncMock` for async adapters (Sprint 1 onward)

Once ports become async, use `AsyncMock`:

```python
from unittest.mock import AsyncMock

camera = AsyncMock(spec=AsyncCameraPort)
camera.capture.return_value = make_fits_frame()

frame = await camera.capture(5.0)
camera.capture.assert_awaited_once_with(5.0)
```

### Pattern 7 — `mocker` fixture from pytest-mock (preferred over manual patch)

`pytest-mock`'s `mocker` fixture auto-stops patches when the test ends — no context manager needed:

```python
def test_astap_timeout(mocker):
    mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("astap", 60))
    solver = AstapSolver(astap_path="/fake/astap")
    result = solver.solve(b"fits", 0.38)
    assert not result.success
```

### Pattern 8 — `autospec=True` catches argument errors

`Mock(spec=Port)` validates method *names*. `create_autospec(Port)` also validates method *signatures*:

```python
from unittest.mock import create_autospec

mount = create_autospec(MountPort)
mount.sync(ra=5.5, dec=-5.4)         # ✓ correct signature
mount.sync(5.5, -5.4, extra="oops")  # ✗ TypeError — signature mismatch
```

Use `create_autospec` for any port method where argument errors are a real risk (e.g. RA/Dec coordinates could be swapped).

---

## Stage isolation — the core pattern

The most important pattern in this codebase: test each stage of `VerticalSliceRunner` by calling the stage method directly, not by calling `run()`.

`run()` tests that 9 stages execute in order. `_stage_align(log)` tests that alignment works correctly. These are different questions. The first is an integration concern; the second is a unit concern.

```python
# Integration test (current approach) — tells you something broke somewhere
def test_solve_fails_session_fails():
    runner, _ = make_runner(solver=MockSolver(always_fail=True))
    log = runner.run()
    assert log.state == SessionState.FAILED

# Unit test (new approach) — tells you exactly what broke and how
def test_align_both_attempts_fail_raises_workflow_error():
    solver = Mock(spec=SolverPort)
    solver.solve.return_value = SolveResult(success=False, error="no stars")
    runner = make_unit_runner(solver=solver)
    log = make_log()
    with pytest.raises(WorkflowError) as exc:
        runner._stage_align(log)
    assert exc.value.stage == "align"
    assert log.plate_solve_attempts == 2        # exhausted both attempts
    assert log.state != SessionState.ALIGNED    # never transitioned
```

The unit test pinpoints the failure. The integration test confirms the whole system handles it.

**Both are needed. The unit test runs in 1 ms. The integration test runs in 50 ms. Run unit tests 50× more often.**

---

## `conftest.py` — shared fixtures

Shared fixtures live in `tests/conftest.py` (pytest discovers it automatically). Fixtures return `Mock(spec=Port)` objects pre-configured for the happy path. Individual tests override specific return values as needed.

See `tests/conftest.py` for the full implementation.

**Design rules for fixtures:**
1. Every port fixture defaults to the happy path. Tests override only what they are testing.
2. Fixtures use `Mock(spec=Port)`, never hand-rolled fakes. Hand-rolled fakes stay in `tests/integration/`.
3. `make_log()` returns a fully-populated `SessionLog`. Tests should never construct SessionLog fields they are not testing.
4. `make_unit_runner(**overrides)` injects the fixture mocks; named overrides replace specific ports.

---

## Directory structure

```
tests/
├── conftest.py                     # shared fixtures — Mock(spec=Port), make_log(), make_unit_runner()
├── unit/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   └── test_session_log.py     # SessionLog.to_dict(), field validation, serialization
│   ├── workflow/
│   │   ├── __init__.py
│   │   ├── test_runner_stages.py   # each stage in isolation — the majority of all tests
│   │   └── test_helpers.py         # _angular_offset_arcmin, _now — pure functions
│   └── adapters/
│       ├── __init__.py
│       ├── astap/
│       │   ├── __init__.py
│       │   ├── test_parse_ini.py   # moved from integration — pure Python, no ASTAP binary
│       │   └── test_subprocess.py  # subprocess mocked — ASTAP timeout, launch failure, no .ini
│       └── mock/
│           ├── __init__.py
│           └── test_mock_contracts.py  # verify fakes honour port contracts
├── integration/
│   ├── __init__.py
│   ├── test_pipeline_fakes.py      # full pipeline with hand-rolled fakes (current tests, renamed)
│   └── test_real_solver_replay.py  # hybrid: real ASTAP + ReplayCamera
└── hardware/
    ├── __init__.py
    └── test_hardware_connect.py    # skipped unless HW_TESTS=1 env var set
```

**Ratio target** (enforced by test naming — pytest counts by directory):

| Directory | Target share | Run in CI |
|---|---|---|
| `tests/unit/` | 70% | Always |
| `tests/integration/` | 20% | Always |
| `tests/hardware/` | 10% | Only when `HW_TESTS=1` |

---

## What the CI gate checks

```yaml
# .github/workflows/test.yml (excerpt)
- name: Lint
  run: ruff check .

- name: Type check
  run: mypy smart_telescope/

- name: Unit + integration tests with coverage
  run: pytest tests/unit/ tests/integration/ -v
  # --cov and --cov-fail-under=80 applied via pyproject.toml

- name: Hardware tests          # separate job, manual trigger only
  if: github.event_name == 'workflow_dispatch'
  env:
    HW_TESTS: "1"
  run: pytest tests/hardware/ -v
```

Hardware tests never run on push. They run on demand before a milestone demo.

---

## What NOT to mock

Not everything should be mocked. Mocking the wrong things creates tests that pass when the real code is broken.

| Do mock | Do not mock |
|---|---|
| Port interfaces (`CameraPort`, `MountPort`, …) | `SessionLog` — it's a data class, test it directly |
| `subprocess.run` in ASTAP adapter tests | `_angular_offset_arcmin` — pure function, test directly |
| `time.sleep` in slew-poll tests | `SessionState` enum — test the transition, not the enum |
| `serial.Serial` in OnStep adapter tests | `WorkflowError` — it's a plain exception, not a collaborator |
| `asyncio.to_thread` in async adapter tests | `datetime.now` — use `freezegun` only if timing is under test |

---

## Parametrize to eliminate repetition

Pytest's `@pytest.mark.parametrize` is the correct tool wherever tests differ only in input/expected values. Use it aggressively for:

```python
@pytest.mark.parametrize("profile,expected_scale", [
    (C8_NATIVE,   0.38),
    (C8_REDUCER,  0.60),
    (C8_BARLOW2X, 0.19),
])
def test_pixel_scale_passed_per_profile(profile, expected_scale, solver_mock):
    runner = make_unit_runner(solver=solver_mock, optical_profile=profile)
    runner._stage_align(make_log())
    _, scale = solver_mock.solve.call_args.args
    assert scale == pytest.approx(expected_scale)
```

Three profiles, one test function, zero duplication. Adding a fourth profile is one line.

---

## Coverage is a floor, not a goal

`--cov-fail-under=80` is a safety net, not a target. 80% coverage with weak assertions is not better than 60% coverage with strong assertions. The questions a test must answer:

1. What behaviour am I specifying?
2. If this code is deleted, will this test fail?
3. If this code has a bug, will this test catch it?

If the answer to question 2 or 3 is "not necessarily," the test is providing false confidence. A mock that is never asserted (`mock.solve.return_value = ...` with no `assert_called`) is a stub, not a test.
