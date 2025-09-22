# Contributing

- Use feature branches and pull requests.
- Keep `ruff` and `mypy` clean.
- Add tests for new features (unit/ui). Hardware-dependent tests go under `tests/integration/` and are marked with `@pytest.mark.integration`.
- New hardware? Add a new adapter under `src/smarttscope/adapters/` implementing the relevant port in `src/smarttscope/domain/ports.py`.
