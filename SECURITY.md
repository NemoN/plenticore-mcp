# Security

## Access

This server authenticates to the inverter as the plant owner. A connected MCP
client can read device data and, when writes are enabled, submit settings changes
within that account's permissions. Battery and grid parameters affect a physical
installation. Their appropriate values depend on its wiring, hardware and local
requirements.

The example configuration sets `PLENTICORE_READ_ONLY=true`. The code default is
`false` if the variable is absent. `update_settings` previews by default;
`dry_run=false` submits the requested values. Validation covers advertised write
access, supported types and numeric bounds. It cannot determine whether a value
is suitable for the installation.

The HTTP listener binds only to loopback and has no MCP authentication. Local
clients with access to that port can call tools. Use stdio or a trusted local
machine; use an SSH tunnel for remote access. The inverter's local HTTP API is
unencrypted unless its HTTPS endpoint is configured. TLS verification defaults
to enabled. Keep the inverter connection on a trusted network.

## Credentials and returned data

Keep `.env` private and outside version control. Source distributions and the
Docker build use file allowlists that exclude local configuration. Passwords and
raw upstream error bodies are omitted from server errors. Password-like setting
IDs are excluded by pattern matching; this does not guarantee that every
sensitive setting on untested firmware will be recognized.

Measurements, settings and event descriptions can contain private information.
Review them before sharing logs or sending tool results to another service.

## Failed writes

Multiple settings are not changed atomically. A transport failure can occur after
the inverter has applied a value. The server does not retry failed network writes
or roll back changes. It retries once after an explicit unauthenticated response.
Read current values before submitting a failed change again.

`verification=mismatch` means the readback differs or is incomplete.
`verification=unavailable` means the write was submitted but the readback failed.
Neither status proves that the original settings remain in place.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/NemoN/plenticore-mcp/security/advisories/new).
Include affected versions, reproduction steps and the expected security boundary.
Use test credentials and remove identifying device details. Do not post working
passwords or session tokens in public issues.

Security fixes target the latest revision on `main`. No response-time commitment
is offered.
