# Changelog

## 0.1.0 (2026-10-25)

Initial version with eleven MCP tools for KOSTAL PLENTICORE inverters.

- Read power measurements, energy statistics, events and current settings.
- Discover modules, measurement IDs and setting metadata from the device.
- Preview settings changes, validate values and read submitted values back.
- Connect over stdio or loopback Streamable HTTP; use `--check` for a read-only connection test.
- Use the plant owner login, with session renewal and an optional write lock.

Live reads and update previews were tested with a PLENTICORE plus 8.5,
firmware `01.30.12092`, API `0.2.0`. Writes were tested against the emulator.
