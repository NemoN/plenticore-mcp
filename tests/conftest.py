"""A local inverter emulator with a real SCRAM/AES handshake and stateful settings."""

import base64
import hashlib
import hmac
import os

import pytest
from aiohttp import web
from Crypto.Cipher import AES

from plenticore_mcp.client import PlenticoreClient
from plenticore_mcp.config import Settings
from plenticore_mcp.tools import PlenticoreTools

PASSWORD = "local-test-password"


@pytest.fixture(autouse=True)
def isolate_device_environment(monkeypatch):
    """Subprocess tests must use the emulator even if the shell has real credentials."""
    for key in tuple(os.environ):
        if key.startswith("PLENTICORE_"):
            monkeypatch.delenv(key)


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode()


class Inverter:
    def __init__(self):
        self.requests = []
        self.logins = 0
        self.expire_next = False
        self.login_error = None
        self.ignore_writes = False
        self.fail_readback = False
        self.omit_values = False
        self.catalog = {
            "devices:local": ["Inverter:State", "Home_P", "Dc_P"],
            "devices:local:pv1": ["P"],
            "devices:local:battery": ["SoC", "P"],
            "scb:statistic:EnergyFlow": ["Statistic:Yield:Day", "Statistic:Yield:Total"],
        }
        self.setting_values = {"Battery:MinSoc": "10", "Name": "Solar", "ReadOnly": "1"}
        self.metadata = [
            {
                "id": "Battery:MinSoc",
                "type": "uint8",
                "min": "5",
                "max": "100",
                "unit": "%",
                "access": "readwrite",
                "default": "10",
            },
            {"id": "Name", "type": "string", "access": "readwrite", "default": None},
            {"id": "ReadOnly", "type": "uint32", "access": "readonly"},
            {
                "id": "Portal:Password",
                "type": "string",
                "access": "readwrite",
                "default": "never-expose-this-secret",
            },
            {"id": "Unsupported", "type": "mystery", "access": "readwrite"},
        ]

    async def handle(self, request):
        path = request.match_info["tail"]
        body = await request.json() if request.can_read_body else None
        self.requests.append((request.method, path, body))
        if path == "auth/start":
            self.logins += 1
            if self.login_error:
                return web.json_response({"message": PASSWORD}, status=self.login_error)
            assert body["username"] == "user"
            nonce = b64(base64.b64decode(body["nonce"]) + b"server-nonce")
            salt = b64(b"test-salt")
            rounds = 100
            self.auth_message = (
                f"n=user,r={body['nonce']},r={nonce},s={salt},i={rounds},c=biws,r={nonce}"
            ).encode()
            salted = hashlib.pbkdf2_hmac("sha256", PASSWORD.encode(), b"test-salt", rounds)
            self.client_key = hmac.digest(salted, b"Client Key", "sha256")
            self.stored_key = hashlib.sha256(self.client_key).digest()
            self.server_key = hmac.digest(salted, b"Server Key", "sha256")
            return web.json_response(
                {
                    "nonce": nonce,
                    "salt": salt,
                    "rounds": rounds,
                    "transactionId": b64(b"transaction"),
                }
            )
        if path == "auth/finish":
            signature = hmac.digest(self.stored_key, self.auth_message, "sha256")
            proof = bytes(a ^ b for a, b in zip(self.client_key, signature, strict=True))
            assert hmac.compare_digest(base64.b64decode(body["proof"]), proof)
            return web.json_response(
                {
                    "token": "auth-token",
                    "signature": b64(hmac.digest(self.server_key, self.auth_message, "sha256")),
                }
            )
        if path == "auth/create_session":
            key = hmac.digest(
                self.stored_key, b"Session Key" + self.auth_message + self.client_key, "sha256"
            )
            cipher = AES.new(key, AES.MODE_GCM, nonce=base64.b64decode(body["iv"]))
            token = cipher.decrypt_and_verify(
                base64.b64decode(body["payload"]), base64.b64decode(body["tag"])
            )
            assert token == b"auth-token"
            return web.json_response({"sessionId": "test-session"})
        if self.expire_next:
            self.expire_next = False
            return web.json_response({"message": "expired"}, status=401)
        if request.headers.get("authorization") != "Session test-session":
            return web.json_response({"message": "login required"}, status=401)
        if path == "auth/logout":
            return web.json_response({})
        if path == "info/version":
            return web.json_response(
                {
                    "name": "PUCK RESTful API",
                    "api_version": "0.2.0",
                    "hostname": "scb",
                    "sw_version": "01.30.12092",
                }
            )
        if path == "auth/me":
            return web.json_response(
                {
                    "active": True,
                    "authenticated": True,
                    "locked": False,
                    "anonymous": False,
                    "role": "user",
                    "permissions": ["read", "write"],
                }
            )
        if path == "modules":
            return web.json_response([{"id": mid, "type": "device"} for mid in self.catalog])
        if path == "processdata" and request.method == "GET":
            return web.json_response(
                [{"moduleid": mid, "processdataids": ids} for mid, ids in self.catalog.items()]
            )
        if path == "processdata":
            return web.json_response(
                [
                    {
                        "moduleid": item["moduleid"],
                        "processdata": [
                            {"id": key, "unit": "%" if key == "SoC" else "W", "value": 42}
                            for key in item["processdataids"]
                            if not self.omit_values
                        ],
                    }
                    for item in body
                ]
            )
        if path == "settings" and request.method == "GET":
            return web.json_response([{"moduleid": "devices:local", "settings": self.metadata}])
        if path == "settings" and request.method == "PUT":
            if not self.ignore_writes:
                self.setting_values.update({x["id"]: x["value"] for x in body[0]["settings"]})
            return web.json_response({})
        if path == "settings":
            if self.fail_readback and any(method == "PUT" for method, _, _ in self.requests):
                return web.json_response({"message": "unavailable"}, status=503)
            return web.json_response(
                [
                    {
                        "moduleid": item["moduleid"],
                        "settings": [
                            {"id": key, "value": self.setting_values[key]}
                            for key in item["settingids"]
                            if key in self.setting_values
                        ],
                    }
                    for item in body
                ]
            )
        if path == "events/latest":
            return web.json_response(
                [
                    {
                        "code": 123,
                        "is_active": True,
                        "end_time": None,
                        "description": "Active test event",
                    }
                ]
            )
        raise AssertionError(f"Unexpected API operation {request.method} {path}")


@pytest.fixture
async def inverter():
    fake = Inverter()
    app = web.Application()
    app.router.add_route("*", "/api/v1/{tail:.*}", fake.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    fake.url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    try:
        yield fake
    finally:
        await runner.cleanup()


@pytest.fixture
async def tools(inverter):
    client = PlenticoreClient(Settings(url=inverter.url, password=PASSWORD, timeout=2))
    try:
        yield PlenticoreTools(client)
    finally:
        await client.close()
