"""Firmware-discovered measurements and validated plant owner settings changes."""

import asyncio
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from .client import PlenticoreClient, PlenticoreError, timestamp

SECRET_ID = re.compile(r"password|passwd|secret|token|privatekey|masterkey|servicecode", re.I)


def page(items: list, offset: int, limit: int) -> dict[str, Any]:
    if offset < 0 or not 1 <= limit <= 500:
        raise PlenticoreError("offset must be >= 0; limit must be between 1 and 500")
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(items) else None,
    }


def validate_selection(selection: dict[str, list[str]], catalog: dict) -> None:
    if not selection or not 1 <= sum(len(ids) for ids in selection.values()) <= 200:
        raise PlenticoreError("Select between 1 and 200 data points per request")
    for module, ids in selection.items():
        if not ids or module not in catalog or any(key not in catalog[module] for key in ids):
            raise PlenticoreError("Unknown module or ID. Discover available IDs first.")


def missing_values(selection: dict, values: dict) -> list[dict]:
    return [
        {"moduleid": module, "id": key}
        for module, ids in selection.items()
        for key in ids
        if key not in values.get(module, {})
    ]


def normalize_setting(value: str, metadata: dict) -> str:
    """Validate known native types, and reject unsupported writable types explicitly."""
    kind = metadata.get("type", "")
    if not isinstance(kind, str):
        raise PlenticoreError("Unsupported setting type; inspect the inverter web interface")
    kind = kind.lower()
    if kind == "byte":
        kind = "uint8"
    if kind in {"bool", "boolean"}:
        if value.lower() not in {"true", "false", "0", "1"}:
            raise PlenticoreError("Boolean settings require true, false, 0 or 1")
        return "1" if value.lower() in {"true", "1"} else "0"
    integer = re.fullmatch(r"(u?)int(8|16|32|64)?", kind)
    if integer or kind in {"float", "float32", "float64", "double"}:
        try:
            number = Decimal(value)
            if not number.is_finite() or (integer and number != number.to_integral_value()):
                raise InvalidOperation
        except InvalidOperation:
            raise PlenticoreError("Setting requires a finite number of the declared type") from None
        if integer:
            unsigned, bits = integer.groups()
            bits = int(bits or 32)
            lower, upper = (
                (0, 2**bits - 1) if unsigned else (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1)
            )
            if not lower <= number <= upper:
                raise PlenticoreError("Setting exceeds its integer type range")
        for bound, lower in (("min", True), ("max", False)):
            raw = metadata.get(bound)
            if raw not in {None, ""}:
                try:
                    boundary = Decimal(str(raw))
                    if not boundary.is_finite():
                        raise InvalidOperation
                except InvalidOperation:
                    raise PlenticoreError(
                        "Cannot validate the setting's advertised bounds"
                    ) from None
                if (lower and number < boundary) or (not lower and number > boundary):
                    raise PlenticoreError("Setting is outside the inverter's advertised min/max")
        return str(int(number)) if integer else str(number)
    if kind in {"string", "str"}:
        if len(value) > 4096 or "\x00" in value:
            raise PlenticoreError("Invalid string setting")
        return value
    raise PlenticoreError("Unsupported setting type; inspect the inverter web interface")


class PlenticoreTools:
    def __init__(self, client: PlenticoreClient):
        self.client = client
        self._write_lock = asyncio.Lock()

    async def status(self) -> dict[str, Any]:
        """Read API/firmware version and plant owner session status."""
        return {
            "observed_at": timestamp(),
            "version": await self.client.call("get_version"),
            "session": await self.client.call("get_me"),
            "read_only": self.client.settings.read_only,
        }

    async def list_modules(self) -> dict[str, Any]:
        """Discover the modules actually offered by this inverter and current user."""
        return {"modules": await self.client.call("get_modules")}

    async def list_process_data(
        self, query: str = "", offset: int = 0, limit: int = 200
    ) -> dict[str, Any]:
        """Discover measurement IDs. Search module/ID; follow next_offset for more."""
        catalog = await self.client.call("get_process_data")
        items = [
            {"moduleid": module, "id": key}
            for module, ids in sorted(catalog.items())
            for key in sorted(ids)
            if query.casefold() in f"{module}/{key}".casefold()
        ]
        return page(items, offset, limit)

    async def read_process_data(self, selection: dict[str, list[str]]) -> dict[str, Any]:
        """Read explicit {moduleid: [IDs]} (max 200), returning native values and units."""
        catalog = await self.client.call("get_process_data")
        validate_selection(selection, catalog)
        return await self._read(selection)

    async def _read(self, selection: dict) -> dict[str, Any]:
        values = await self.client.call("get_process_data_values", selection) if selection else {}
        return {
            "observed_at": timestamp(),
            "values": values,
            "missing": missing_values(selection, values),
        }

    async def overview(self) -> dict[str, Any]:
        """Read power flow, AC, PV strings, battery and meter measurements that exist."""
        catalog = await self.client.call("get_process_data")
        modules = {
            "devices:local",
            "devices:local:ac",
            "devices:local:pv1",
            "devices:local:pv2",
            "devices:local:pv3",
            "devices:local:battery",
            "devices:local:powermeter",
        }
        result = await self._read(
            {mid: ids for mid, ids in catalog.items() if mid in modules and ids}
        )
        result["notes"] = [
            "Native inverter units and signs are preserved; check each returned unit.",
            "devices:local/Dc_P can include battery power; PV string power is returned separately.",
            "Missing battery or grid meter modules can mean hardware is absent or unavailable.",
        ]
        return result

    async def battery(self) -> dict[str, Any]:
        """Read available battery measurements, including SoC and power."""
        catalog = await self.client.call("get_process_data")
        selection = {}
        for mid, ids in catalog.items():
            selected = [
                key
                for key in ids
                if "battery" in mid.lower()
                or "battery" in key.lower()
                or key in {"HomeBat_P", "SoC"}
            ]
            if selected:
                selection[mid] = selected
        result = await self._read(selection)
        result["available"] = bool(selection)
        result["notes"] = (
            "Availability describes measurements, not the presence of a physical battery."
        )
        return result

    async def energy(
        self, period: Literal["Day", "Month", "Year", "Total"] = "Day"
    ) -> dict[str, Any]:
        """Read inverter-native energy counters for Day, Month, Year or Total. Preserve units."""
        catalog = await self.client.call("get_process_data")
        selection = {
            mid: [key for key in ids if key.startswith("Statistic:") and key.endswith(":" + period)]
            for mid, ids in catalog.items()
        }
        result = await self._read({mid: ids for mid, ids in selection.items() if ids})
        result["period"] = period
        result["notes"] = (
            "Periods follow the inverter clock. Counters are not arbitrary date ranges."
        )
        return result

    async def events(
        self, limit: int = 20, language: Literal["de-de", "en-gb"] = "de-de"
    ) -> dict[str, Any]:
        """Read the latest 1–100 inverter events; active events may have end_time=null."""
        if not 1 <= limit <= 100:
            raise PlenticoreError("Event limit must be between 1 and 100")
        return {
            "observed_at": timestamp(),
            "events": await self.client.call("get_events", max_count=limit, lang=language),
        }

    async def _settings(self) -> dict[str, Any]:
        data = await self.client.call("get_settings")
        return {
            mid: {
                item["id"]: item for item in items if not SECRET_ID.search(mid + "/" + item["id"])
            }
            for mid, items in data.items()
        }

    async def list_settings(
        self, query: str = "", offset: int = 0, limit: int = 200
    ) -> dict[str, Any]:
        """Discover setting types, units, access rights and min/max. Secrets are omitted."""
        catalog = await self._settings()
        items = [
            {**meta, "moduleid": mid}
            for mid, settings in sorted(catalog.items())
            for key, meta in sorted(settings.items())
            if query.casefold() in f"{mid}/{key}".casefold()
        ]
        return page(items, offset, limit)

    async def read_settings(self, selection: dict[str, list[str]]) -> dict[str, Any]:
        """Read explicit {moduleid: [setting IDs]}. Discover IDs first; secrets are excluded."""
        catalog = await self._settings()
        validate_selection(selection, catalog)
        values = await self.client.call("get_setting_values", selection)
        return {
            "observed_at": timestamp(),
            "values": values,
            "missing": missing_values(selection, values),
        }

    async def update_settings(
        self, moduleid: str, values: dict[str, str], dry_run: bool = True
    ) -> dict[str, Any]:
        """Preview settings changes; dry_run=false writes and reads back. Values are strings.

        Uses actual owner-accessible IDs, types and min/max. No installer login. Read list_settings
        and the current values first. Multi-setting writes are not atomic; no automatic rollback.
        A connection error after submission can leave a change applied: read back before retrying.
        """
        async with self._write_lock:
            catalog = await self._settings()
            if not 1 <= len(values) <= 20:
                raise PlenticoreError("Change between 1 and 20 settings per call")
            validate_selection({moduleid: list(values)}, catalog)
            normalized = {}
            for key, value in values.items():
                metadata = catalog[moduleid][key]
                if metadata.get("access") not in {"readwrite", "writeonly"}:
                    raise PlenticoreError(
                        "Setting is not advertised as writable for the current user"
                    )
                if metadata.get("access") == "writeonly":
                    raise PlenticoreError(
                        "Write-only settings cannot be verified and are unsupported"
                    )
                normalized[key] = normalize_setting(value, metadata)
            before = await self.client.call("get_setting_values", {moduleid: list(values)})
            if missing_values({moduleid: list(values)}, before):
                raise PlenticoreError("Current values are incomplete; no settings were written")
            result = {
                "dry_run": dry_run,
                "moduleid": moduleid,
                "before": before[moduleid],
                "requested": normalized,
                "write_enabled": not self.client.settings.read_only,
            }
            if dry_run:
                return result
            try:
                await self.client.call("set_setting_values", moduleid, normalized)
            except PlenticoreError as exc:
                raise PlenticoreError(
                    "Settings submission failed; the outcome may be uncertain. "
                    "Read current values before retrying. " + str(exc)
                ) from None
            try:
                after = await self.client.call("get_setting_values", {moduleid: list(values)})
            except PlenticoreError:
                return {
                    **result,
                    "verification": "unavailable",
                    "warning": (
                        "Write was submitted; readback failed. "
                        "Read current settings before retrying."
                    ),
                }
            actual = after.get(moduleid, {})
            matches = {}
            for key, value in normalized.items():
                try:
                    meta = catalog[moduleid][key]
                    observed = normalize_setting(actual[key], meta)
                    if meta.get("type") in {"float", "float32", "float64", "double"}:
                        matches[key] = Decimal(observed) == Decimal(value)
                    else:
                        matches[key] = observed == value
                except (KeyError, PlenticoreError, AttributeError, TypeError):
                    matches[key] = False
            return {
                **result,
                "after": actual,
                "matches": matches,
                "verification": "matched" if all(matches.values()) else "mismatch",
            }
