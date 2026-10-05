# itqan pack: Python

Read the project's facts first: `requires-python` and tool config in `pyproject.toml`
(ruff, mypy/pyright, pytest), the framework (Django, FastAPI, Flask, none), and how
dependencies are managed (uv, poetry, pip-tools). Follow what the project already does.

## Implementing
- **Types:** annotate public functions; `from __future__ import annotations` if the project
  uses it; `X | None` instead of `Optional[X]` on 3.10+.
- **Errors:** catch specific exceptions, never a bare `except:`; don't swallow errors silently;
  raise with context (`raise NewError(...) from exc`).
- **No mutable defaults:** `def f(items=None): items = items or []`, not `def f(items=[])`.
- **Resources:** `with` for files, locks, connections; `pathlib.Path` instead of string paths.
- **Time:** timezone-aware datetimes (`datetime.now(timezone.utc)`), never naive `utcnow()`.
- **Logging:** `logger.info("paid %s", order_id)` (lazy formatting), no secrets in logs, a
  module-level `logger = logging.getLogger(__name__)`.
- **Data:** `dataclass` / pydantic models for structured data instead of loose dicts.
- **Subprocess:** argument lists, no `shell=True` with anything user-controlled; always a timeout.
- **HTTP:** always pass `timeout=` (requests/httpx); reuse a session/client.

## Security
- SQL with parameters only (`cursor.execute("... where id = %s", (id,))` / ORM), never f-strings.
- `yaml.safe_load`, never `yaml.load`; never unpickle untrusted data.
- Check paths built from input stay inside the intended folder (`resolve()` + `is_relative_to`).
- Secrets from the environment / a vault; `.env` in `.gitignore`.

## Testing (pytest)
- One behaviour per test; names say what they prove (`test_total_applies_discount`).
- `@pytest.mark.parametrize` for input tables; fixtures for setup; `tmp_path` for files;
  `monkeypatch` for env vars and attributes; freeze or inject time.
- Assert on behaviour and outputs, not on private implementation details.

## Review checklist (bugs that bite)
- [ ] mutable default arguments; shared state mutated across calls
- [ ] bare/broad `except` hiding failures; exceptions lost in threads/async tasks
- [ ] missing `await`, or blocking I/O inside `async def`
- [ ] naive datetimes, local time in logic
- [ ] requests/httpx without timeout; subprocess with `shell=True` and input
- [ ] SQL or shell built with f-strings; unsafe yaml/pickle
- [ ] off-by-one in slicing/ranges; `is` used for value comparison
- [ ] new behaviour without a test

## Commands
`python -m pytest -q` · `ruff check .` · `ruff format --check .` · `mypy .` (if configured) ·
with barq: `barq run:test run:lint`
