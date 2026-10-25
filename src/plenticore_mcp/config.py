"""Explicit connection configuration. Passwords are excluded from representations."""

import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    url: str
    password: str = field(repr=False)
    timeout: float = 20
    verify_ssl: bool = True
    read_only: bool = False

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.url)
            port = parsed.port
            valid = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
                and (port is None or 1 <= port <= 65535)
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("PLENTICORE_URL needs an HTTP(S) base URL without path or credentials")
        if not self.password or self.password == "replace-locally":
            raise ValueError("Set PLENTICORE_PASSWORD locally to the plant owner password")
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 300:
            raise ValueError("PLENTICORE_TIMEOUT must be between 0 (exclusive) and 300 seconds")

    @classmethod
    def from_env(cls) -> "Settings":
        verify = os.getenv("PLENTICORE_VERIFY_SSL", "true").strip().lower()
        if verify not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError("PLENTICORE_VERIFY_SSL must be true or false")
        read_only = os.getenv("PLENTICORE_READ_ONLY", "false").strip().lower()
        if read_only not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError("PLENTICORE_READ_ONLY must be true or false")
        try:
            timeout = float(os.getenv("PLENTICORE_TIMEOUT", "20"))
        except ValueError:
            raise ValueError("PLENTICORE_TIMEOUT must be a number") from None
        return cls(
            url=os.getenv("PLENTICORE_URL", "").strip().rstrip("/"),
            password=os.getenv("PLENTICORE_PASSWORD", ""),
            timeout=timeout,
            verify_ssl=verify in {"true", "1", "yes"},
            read_only=read_only in {"true", "1", "yes"},
        )
