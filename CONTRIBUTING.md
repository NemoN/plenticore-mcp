# Contributing

Open an issue for a reproducible problem or submit a pull request with a fix.
English and German reports are welcome.

For compatibility reports, include the inverter model, firmware version, API
version, tool name and error message. Remove passwords, session tokens, serial
numbers and identifying network details. Do not attach a complete `.env` or an
unreviewed device export.

## Local checks

```bash
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv run --frozen ruff format --check src tests scripts
uv run --frozen python scripts/generate_tool_reference.py --check
uv build
uv run --frozen python scripts/check_artifacts.py dist/*.whl dist/*.tar.gz
```

Tests run against a local emulator. Keep them independent of real inverters and
credentials. Changes to settings validation or transport behavior need tests
that exercise the affected request or failure path.

After changing tool signatures or descriptions, regenerate the reference:

```bash
uv run --frozen python scripts/generate_tool_reference.py
```

After changing dependencies, update both lockfiles:

```bash
uv lock
uv export --frozen --no-dev --no-emit-project --no-header --output-file requirements.lock > /dev/null
```

The runtime export is used by the Docker build. CI checks it against `uv.lock`.
Keep public examples generic. Submit vulnerability reports through the private
route in [SECURITY.md](SECURITY.md).
