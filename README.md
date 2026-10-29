# PLENTICORE MCP

[![CI](https://github.com/NemoN/plenticore-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/NemoN/plenticore-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

<a href="https://www.buymeacoffee.com/nemon" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/white_img.png" alt="Buy Me A Coffee" style="height: auto !important;width: auto !important;" ></a>

English · [Deutsch](README.de.md)

An MCP server for KOSTAL PLENTICORE inverters. Read power, energy counters and
events, inspect settings, and change settings available to the plant owner.
The server connects to the inverter's local REST API using
[pykoplenti](https://github.com/stegm/pykoplenti) and the
[official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

Tested with a PLENTICORE plus 8.5 running firmware `01.30.12092`, API `0.2.0`.
Other models and firmware versions have not been tested. Available measurements
and settings are discovered from the connected device.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python
3.11 or newer, then clone the repository:

```bash
git clone https://github.com/NemoN/plenticore-mcp.git
cd plenticore-mcp
uv sync --frozen
cp .env.example .env
chmod 600 .env
```

Edit `.env` with your inverter's address and the plant owner password from its
local web interface:

```dotenv
PLENTICORE_URL=http://plenticore.example
PLENTICORE_PASSWORD=replace-locally
PLENTICORE_TIMEOUT=20
PLENTICORE_VERIFY_SSL=true
PLENTICORE_READ_ONLY=true
```

Use the base URL without `/api/v1`. The example starts in read-only mode. Set
`PLENTICORE_READ_ONLY=false` when you want to apply settings changes. If omitted,
the code default is `false`; update calls still preview by default.

Check the login and current readings:

```bash
uv run --frozen plenticore-mcp --check
```

The check reads status and measurements without changing device settings.
Exit code 0 means success; 1 indicates a connection or API error; 2 indicates
invalid configuration. Starting without `--check` waits for an MCP client.

## Connect an MCP client

For clients using `mcpServers` JSON, replace the two absolute paths:

```json
{
  "mcpServers": {
    "plenticore": {
      "command": "uv",
      "args": [
        "run", "--frozen", "--directory", "/absolute/path/plenticore-mcp",
        "plenticore-mcp", "--env-file", "/absolute/path/plenticore.env"
      ]
    }
  }
}
```

The env file can be the checkout's `.env` or a separate private file. If the
client cannot find `uv`, use its full executable path. The client starts the
stdio process when needed. Standard output is reserved for the MCP protocol.

[examples/](examples/) contains JSON and Codex TOML configurations.
See [configuration](docs/configuration.md) for environment variables, HTTPS and
remote connections.

### Streamable HTTP

```bash
uv run --frozen plenticore-mcp --transport streamable-http --port 8001
```

Connect to `http://127.0.0.1:8001/mcp`. The listener binds to loopback and has no
MCP authentication. Use an SSH tunnel for access from another machine.

## Tools

All names start with `plenticore_`. The [tool reference](docs/tools.md) lists
their arguments and defaults.

| Tool, without prefix | Purpose |
| --- | --- |
| `status` | API and firmware versions, session status, read-only mode |
| `list_modules` | Modules offered by the inverter |
| `list_process_data` | Search measurement IDs, with pagination |
| `read_process_data` | Read selected measurements |
| `overview` | Power flow, AC, PV strings, battery and grid meter, where available |
| `battery` | Battery-related readings, where available |
| `energy` | Energy statistics for `Day`, `Month`, `Year` or `Total` |
| `events` | Recent events in German or English |
| `list_settings` | Setting IDs, types, units, access rights and bounds |
| `read_settings` | Read selected current settings |
| `update_settings` | Preview changes, or write and read them back |

Example requests for a connected assistant:

> Show today's yield, this month's yield and the current AC output.

> List the battery settings and their current values. Prepare a preview of the
> change I request before applying it.

## Readings and units

Values and signs are returned as supplied by the inverter. Some firmware sends
an empty `unit`; an empty unit does not mean that the value is dimensionless.
`Dc_P` can include battery power. Use the individual PV string measurements when
you need solar input power.

Energy periods follow the inverter clock. The server has no historical database
or arbitrary date-range query. Missing measurements appear under `missing`;
non-finite numeric values become JSON `null`. A battery-related data point does
not establish that a physical battery is installed.

## Settings changes

Read `list_settings` and `read_settings` before changing a value. Pass setting
values as strings in the inverter's native units. `update_settings` defaults to
`dry_run=true` and returns the current and proposed values. Set `dry_run=false`
to submit the change and read it back.

The server checks advertised access rights, supported data types and numeric
bounds. It rejects unknown IDs, unsupported types and write-only settings.
Password and token settings recognized by their IDs are excluded. The inverter
enforces the plant owner's permissions; installer access is not implemented.

Writes are not atomic. A failed request may leave some changes applied. Read
the current settings before retrying. The result reports `verification` as
`matched`, `mismatch` or `unavailable`; it does not perform an automatic rollback.
`PLENTICORE_READ_ONLY=true` blocks writes while allowing previews.

See [SECURITY.md](SECURITY.md) for access and reporting details.

## Docker

```bash
docker build -t plenticore-mcp .
docker run --rm -i --env-file .env plenticore-mcp
```

Use `-i` without `-t` for stdio. The inverter must be reachable from the
container. The image runs as an unprivileged user and installs hashed runtime
dependencies from `requirements.lock`. No prebuilt container image is published.

## Development

```bash
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv run --frozen ruff format --check src tests scripts
uv run --frozen python scripts/generate_tool_reference.py --check
uv build
uv run --frozen python scripts/check_artifacts.py dist/*.whl dist/*.tar.gz
```

Tests use a local inverter emulator, including the login handshake, and real MCP
stdio and HTTP connections. They do not require a physical inverter. Live
validation covered all eleven tools; the update tool was tested as a preview.
Actual writes and readback failures have been tested against the emulator only.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## Project information

MIT licensed. Independent project, not affiliated with KOSTAL Solar Electric.
Report reproducible problems through [GitHub Issues](https://github.com/NemoN/plenticore-mcp/issues).
Remove credentials and identifying device details from reports and logs.
