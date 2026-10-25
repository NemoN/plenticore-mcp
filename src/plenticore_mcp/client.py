"""Serialized, lazily authenticated requests using pykoplenti's SCRAM/AES login."""

import asyncio
import contextlib
from collections.abc import Mapping
from datetime import UTC, datetime

import aiohttp
from pydantic import BaseModel, ValidationError
from pykoplenti import (
    ApiClient,
    ApiException,
    AuthenticationException,
    NotAuthorizedException,
    UserLockedException,
)
from yarl import URL

from .config import Settings


class PlenticoreError(RuntimeError):
    """An actionable error without credentials or raw upstream responses."""


class LocalApiClient(ApiClient):
    def __init__(self, session: aiohttp.ClientSession, url: str):
        self.base_url = URL(url) / "api" / "v1" / ""
        super().__init__(session, self.base_url.host, self.base_url.port)

    def _create_url(self, path: str) -> URL:
        # pykoplenti defaults to HTTP. Preserve the configured scheme and port.
        return self.base_url.join(URL(path))

    async def invoke(self, operation: str, *args, **kwargs):
        """Read raw JSON so optional fields and firmware metadata are preserved."""
        method = "GET"
        payload = None
        paths = {
            "get_version": "info/version",
            "get_me": "auth/me",
            "get_modules": "modules",
            "get_process_data": "processdata",
            "get_settings": "settings",
            "get_process_data_values": "processdata",
            "get_setting_values": "settings",
            "set_setting_values": "settings",
            "get_events": "events/latest",
        }
        if operation in {"get_process_data_values", "get_setting_values"}:
            method = "POST"
            key = "processdataids" if operation == "get_process_data_values" else "settingids"
            payload = [{"moduleid": mid, key: ids} for mid, ids in args[0].items()]
        elif operation == "set_setting_values":
            method = "PUT"
            payload = [
                {
                    "moduleid": args[0],
                    "settings": [{"id": key, "value": value} for key, value in args[1].items()],
                }
            ]
        elif operation == "get_events":
            method = "POST"
            payload = {"max": kwargs["max_count"], "language": kwargs["lang"]}
        request_options = {"json": payload} if payload is not None else {}
        async with self._session_request(
            paths[operation], method=method, **request_options
        ) as resp:
            await self._check_response(resp)
            if operation == "set_setting_values":
                return None
            data = await resp.json()
        if operation == "get_process_data":
            return {item["moduleid"]: item["processdataids"] for item in data}
        if operation == "get_settings":
            return {item["moduleid"]: item["settings"] for item in data}
        if operation == "get_process_data_values":
            return {item["moduleid"]: {x["id"]: x for x in item["processdata"]} for item in data}
        if operation == "get_setting_values":
            return {
                item["moduleid"]: {x["id"]: x["value"] for x in item["settings"]} for item in data
            }
        return data


def json_value(value):
    """Convert library models and mappings to strict JSON, preserving raw units."""
    if isinstance(value, BaseModel):
        return json_value(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, float):
        import math

        return value if math.isfinite(value) else None
    return value


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class PlenticoreClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None
        self._api: LocalApiClient | None = None
        self._authenticated = False

    async def call(self, method: str, *args, **kwargs):
        # No generic HTTP endpoint is exposed to the MCP client.
        if method not in {
            "get_version",
            "get_me",
            "get_modules",
            "get_process_data",
            "get_process_data_values",
            "get_settings",
            "get_setting_values",
            "get_events",
            "set_setting_values",
        }:
            raise PlenticoreError("Unsupported API operation")
        if method == "set_setting_values" and self.settings.read_only:
            raise PlenticoreError("Settings changes are disabled by PLENTICORE_READ_ONLY")
        async with self._lock:
            try:
                async with asyncio.timeout(self.settings.timeout):
                    if self._session is None:
                        self._session = aiohttp.ClientSession(
                            timeout=aiohttp.ClientTimeout(total=self.settings.timeout),
                            connector=aiohttp.TCPConnector(ssl=self.settings.verify_ssl),
                            trust_env=False,
                        )
                        self._api = LocalApiClient(self._session, self.settings.url)
                    if not self._authenticated:
                        await self._api.login(self.settings.password)
                        self._authenticated = True
                    try:
                        result = await self._api.invoke(method, *args, **kwargs)
                    except NotAuthorizedException:
                        # Only an explicitly unauthenticated request is retried.
                        self._authenticated = False
                        await self._api.login(self.settings.password)
                        self._authenticated = True
                        result = await self._api.invoke(method, *args, **kwargs)
                    return json_value(result)
            except UserLockedException:
                self._authenticated = False
                raise PlenticoreError(
                    "The inverter account is locked. Check the local web interface before retrying."
                ) from None
            except (AuthenticationException, NotAuthorizedException):
                self._authenticated = False
                raise PlenticoreError(
                    "Login failed. Check PLENTICORE_PASSWORD (plant owner password)."
                ) from None
            except TimeoutError:
                raise PlenticoreError(
                    "Inverter request timed out. Check host and connectivity."
                ) from None
            except aiohttp.ClientError:
                raise PlenticoreError(
                    "Cannot reach inverter API. Check PLENTICORE_URL, network and TLS certificate."
                ) from None
            except ApiException:
                raise PlenticoreError(
                    "The inverter rejected the API request. Check firmware, IDs and permissions."
                ) from None
            except (ValidationError, ValueError, KeyError, TypeError):
                raise PlenticoreError(
                    "Unexpected inverter response; check API compatibility."
                ) from None
            except Exception:
                # Includes signature mismatch in pykoplenti's login implementation.
                raise PlenticoreError(
                    "Inverter communication failed; check API compatibility."
                ) from None

    async def close(self) -> None:
        async with self._lock:
            if self._session is not None:
                try:
                    if self._authenticated and self._api is not None:
                        with contextlib.suppress(Exception):
                            async with asyncio.timeout(min(self.settings.timeout, 3)):
                                await self._api.logout()
                finally:
                    await self._session.close()
                    self._session = None
                    self._api = None
                    self._authenticated = False
