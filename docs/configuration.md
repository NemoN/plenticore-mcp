# Configuration

## Environment variables

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `PLENTICORE_URL` | Yes | None | Inverter base URL, such as `http://plenticore.example` |
| `PLENTICORE_PASSWORD` | Yes | None | Plant owner password from the local web interface |
| `PLENTICORE_TIMEOUT` | No | `20` | Per-call timeout in seconds, greater than 0 and at most 300 |
| `PLENTICORE_VERIFY_SSL` | No | `true` | Verify the inverter's HTTPS certificate |
| `PLENTICORE_READ_ONLY` | No | `false` | Block writes; reads and previews remain available |

Boolean variables accept `true`, `false`, `1`, `0`, `yes` and `no`, ignoring case.
The example `.env` enables read-only mode. Process variables take precedence over
values loaded from the file.

The URL accepts HTTP or HTTPS and an optional port. It must not contain a path,
query string, fragment or credentials. The server adds `/api/v1` itself.
Use the password from the local web interface, not a KOSTAL portal password or
an installer service code.

By default the command loads `.env` from its current working directory. Use an
explicit path when an MCP client starts the process elsewhere:

```bash
uv run --frozen plenticore-mcp --env-file /absolute/path/plenticore.env
```

Configuration is validated at startup. The server connects and logs in on the
first tool call. Listing tools or reading `plenticore://usage` does not contact
the inverter. Sessions are reused and renewed after an unauthenticated response.
The server attempts to log out on shutdown.

## Connection check

```bash
uv run --frozen plenticore-mcp --env-file /absolute/path/plenticore.env --check
```

The check returns JSON containing `status` and `overview`, or an `error` message.
It writes no device settings. Exit codes are 0 for success, 1 for a connection or
API failure, and 2 for invalid arguments or configuration.

## Transport

The default is stdio. The client launches the process and uses stdin/stdout
for the protocol. Server diagnostics go to stderr.

Streamable HTTP uses loopback and port 8001 by default:

```bash
uv run --frozen plenticore-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

Allowed bind addresses are `127.0.0.1`, `::1` and `localhost`. The endpoint is
`/mcp`. The listener has no MCP authentication; see [SECURITY.md](../SECURITY.md).

### Remote host

Run the HTTP command on a machine that can reach the inverter. From the client
machine, forward the port:

```bash
ssh -N -L 8001:127.0.0.1:8001 user@server.example
```

Point the MCP client at `http://127.0.0.1:8001/mcp`. Adapt the hostname, user and
ports to your setup.

## Readings

Use `list_process_data` to find measurement IDs before passing a selection to
`read_process_data`. Entries retain the raw `id`, `value` and `unit` fields.
Some firmware returns an empty unit string. Look up the field's unit before
interpreting it; the server does not infer or convert units.

`energy` selects `Statistic:*` fields for the requested device period. Responses
can include energy counters, percentages and CO2 statistics. These fields do not
all share a unit. Periods are `Day`, `Month`, `Year` and `Total`; they follow the
inverter clock.

`available` in `battery` means battery-related measurements were found. It does
not confirm that a battery is attached. An absent module or missing reading must
not be treated as a measured zero.

## Settings and verification

`read_settings` and `read_process_data` accept at most 200 selected IDs per call.
`list_settings` and `list_process_data` default to 200 results and allow up to
500 per page. Follow `next_offset` until it is `null`.

`update_settings` accepts 1 to 20 values within one module. It reads metadata
from the connected inverter on each call. Supported writable types are
`bool`/`boolean`, `byte`, signed and unsigned integers with 8, 16, 32 or 64 bits,
`float`/`float32`/`float64`/`double`, and `string`/`str`. Bare `int` and `uint` use
32-bit ranges. Numeric `min` and `max` bounds are checked when supplied.

Boolean strings normalize to `0` or `1`. Integer strings must represent whole
numbers. NaN and infinity are rejected. Strings are limited to 4096 characters
and must not contain NUL. Unsupported types, write-only settings and IDs
recognized as secrets are rejected.

Previews include `before`, `requested` and `write_enabled`. Writes also return
the available `after` values, per-field `matches` and a `verification` status.
Numerically equal floating-point representations compare as equal. The server
does not wait for a delayed effect or roll back a mismatch.
