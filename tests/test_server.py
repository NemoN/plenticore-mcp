import asyncio
import json
import socket
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from plenticore_mcp.client import PlenticoreClient, PlenticoreError, json_value
from plenticore_mcp.config import Settings
from plenticore_mcp.server import READ_TOOLS, build_server
from plenticore_mcp.tools import PlenticoreTools, normalize_setting

from .conftest import PASSWORD

PROJECT = Path(__file__).resolve().parents[1]


async def test_real_login_reuse_and_expired_session(tools, inverter):
    status = await tools.status()
    assert status["version"]["sw_version"] == "01.30.12092"
    assert status["session"]["authenticated"] is True
    assert inverter.logins == 1
    inverter.expire_next = True
    await tools.list_settings()
    assert inverter.logins == 2
    assert all("password" not in json.dumps(body or {}).lower() for _, _, body in inverter.requests)


async def test_measurements_and_optional_fields(tools, inverter):
    overview = await tools.overview()
    assert overview["values"]["devices:local:pv1"]["P"]["unit"] == "W"
    assert (await tools.battery())["available"] is True
    energy = await tools.energy("Total")
    assert "Statistic:Yield:Total" in energy["values"]["scb:statistic:EnergyFlow"]
    assert (await tools.events())["events"][0]["end_time"] is None
    page = await tools.list_process_data(query="devices:local", limit=1)
    assert page["next_offset"] == 1
    assert page["total"] > 1
    with pytest.raises(PlenticoreError, match="Unknown"):
        await tools.read_process_data({"devices:local/../../system": ["reboot"]})
    inverter.omit_values = True
    missing = await tools.read_process_data({"devices:local": ["Home_P"]})
    assert missing["missing"] == [{"moduleid": "devices:local", "id": "Home_P"}]
    del inverter.catalog["devices:local:battery"]
    assert (await tools.battery())["available"] is False
    assert json_value(float("nan")) is None
    assert json_value(float("inf")) is None


async def test_preview_write_and_readback(tools, inverter):
    preview = await tools.update_settings("devices:local", {"Battery:MinSoc": "20"})
    assert preview["before"] == {"Battery:MinSoc": "10"}
    assert preview["requested"] == {"Battery:MinSoc": "20"}
    assert not any(method == "PUT" for method, _, _ in inverter.requests)
    result = await tools.update_settings("devices:local", {"Battery:MinSoc": "20"}, dry_run=False)
    assert result["after"] == {"Battery:MinSoc": "20"}
    assert result["verification"] == "matched"
    inverter.ignore_writes = True
    result = await tools.update_settings("devices:local", {"Battery:MinSoc": "30"}, dry_run=False)
    assert result["verification"] == "mismatch"


@pytest.mark.parametrize(
    "values",
    [
        {"Battery:MinSoc": "101"},
        {"Battery:MinSoc": "NaN"},
        {"Battery:MinSoc": "20.5"},
        {"ReadOnly": "2"},
        {"Unsupported": "x"},
        {"Portal:Password": "secret"},
        {},
    ],
)
async def test_invalid_settings_never_write(tools, inverter, values):
    with pytest.raises(PlenticoreError):
        await tools.update_settings("devices:local", values, dry_run=False)
    assert not any(method == "PUT" for method, _, _ in inverter.requests)


async def test_secrets_are_excluded(tools):
    metadata = await tools.list_settings()
    assert "never-expose" not in json.dumps(metadata)
    assert "Portal:Password" not in json.dumps(metadata)
    with pytest.raises(PlenticoreError):
        await tools.read_settings({"devices:local": ["Portal:Password"]})


async def test_read_only_and_failed_verification(inverter):
    client = PlenticoreClient(Settings(url=inverter.url, password=PASSWORD, read_only=True))
    tools = PlenticoreTools(client)
    try:
        assert (await tools.update_settings("devices:local", {"Name": "New"}))[
            "write_enabled"
        ] is False
        with pytest.raises(PlenticoreError, match="READ_ONLY"):
            await tools.update_settings("devices:local", {"Name": "New"}, dry_run=False)
        assert not any(method == "PUT" for method, _, _ in inverter.requests)
    finally:
        await client.close()
    client = PlenticoreClient(Settings(url=inverter.url, password=PASSWORD))
    try:
        inverter.fail_readback = True
        result = await PlenticoreTools(client).update_settings(
            "devices:local", {"Name": "New"}, dry_run=False
        )
        assert result["verification"] == "unavailable"
        assert inverter.setting_values["Name"] == "New"
    finally:
        await client.close()


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_login_errors_hide_upstream_secrets(tools, inverter, status):
    inverter.login_error = status
    with pytest.raises(PlenticoreError) as error:
        await tools.status()
    assert PASSWORD not in str(error.value)
    assert inverter.logins == 1


async def test_parallel_calls_share_one_session(tools, inverter):
    await asyncio.gather(tools.status(), tools.overview(), tools.events())
    assert inverter.logins == 1


async def test_mcp_tools_resources_and_validation(tools, inverter):
    async with Client(build_server(tools)) as client:
        result = await client.list_tools()
        indexed = {tool.name: tool for tool in result.tools}
        assert set(indexed) == {"plenticore_" + name for name in READ_TOOLS | {"update_settings"}}
        assert not inverter.requests  # listing does not authenticate or touch the inverter
        assert indexed["plenticore_status"].annotations.read_only_hint is True
        update = indexed["plenticore_update_settings"]
        assert update.annotations.read_only_hint is False
        assert update.input_schema["properties"]["dry_run"]["default"] is True
        status = await client.call_tool("plenticore_status", {})
        assert not status.is_error
        assert status.structured_content["version"]["api_version"] == "0.2.0"
        error = await client.call_tool(
            "plenticore_read_settings", {"selection": {"devices:local": ["Portal:Password"]}}
        )
        assert error.is_error
        usage = await client.read_resource("plenticore://usage")
        assert "not atomic" in usage.contents[0].text


async def test_stdio_subprocess(inverter, tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text(f"PLENTICORE_URL={inverter.url}\nPLENTICORE_PASSWORD={PASSWORD}\n")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "plenticore_mcp", "--env-file", str(env_file)],
        cwd=str(PROJECT),
        env={"PLENTICORE_URL": inverter.url, "PLENTICORE_PASSWORD": PASSWORD},
    )
    async with Client(params) as client:
        assert len((await client.list_tools()).tools) == 11
        assert not inverter.requests
        result = await client.call_tool("plenticore_overview", {})
        assert not result.is_error
        assert result.structured_content["values"]["devices:local"]["Home_P"]["value"] == 42


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://inverter",
        "http://u:p@host",
        "http://host/api/v1",
        "http://host:0",
        "http://host:70000",
        "http://host?query=1",
    ],
)
def test_invalid_urls(url):
    with pytest.raises(ValueError, match="PLENTICORE_URL"):
        Settings(url=url, password=PASSWORD)


def test_config_password_and_types(monkeypatch):
    assert PASSWORD not in repr(Settings(url="https://inverter:443", password=PASSWORD))
    with pytest.raises(ValueError, match="PASSWORD"):
        Settings(url="http://host", password="")
    with pytest.raises(ValueError, match="TIMEOUT"):
        Settings(url="http://host", password=PASSWORD, timeout=float("inf"))
    monkeypatch.setenv("PLENTICORE_VERIFY_SSL", "perhaps")
    with pytest.raises(ValueError, match="VERIFY_SSL"):
        Settings.from_env()
    assert normalize_setting("true", {"type": "bool"}) == "1"
    assert normalize_setting("10.0", {"type": "uint32"}) == "10"
    assert normalize_setting("255", {"type": "byte"}) == "255"
    with pytest.raises(PlenticoreError):
        normalize_setting("256", {"type": "byte"})
    with pytest.raises(PlenticoreError):
        normalize_setting("-1", {"type": "uint32"})


async def test_check_cli_is_read_only(inverter):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "plenticore_mcp",
        "--check",
        cwd=PROJECT,
        env={
            "PATH": str(Path(sys.executable).parent),
            "PLENTICORE_URL": inverter.url,
            "PLENTICORE_PASSWORD": PASSWORD,
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), 15)
    assert proc.returncode == 0, stderr.decode()
    assert json.loads(stdout)["status"]["session"]["authenticated"] is True
    assert PASSWORD.encode() not in stdout + stderr
    assert not any(method == "PUT" for method, _, _ in inverter.requests)


async def test_http_transport(inverter, tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env_file = tmp_path / "http.env"
    env_file.write_text(f"PLENTICORE_URL={inverter.url}\nPLENTICORE_PASSWORD={PASSWORD}\n")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "plenticore_mcp",
        "--env-file",
        str(env_file),
        "--transport",
        "streamable-http",
        "--port",
        str(port),
        cwd=PROJECT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with asyncio.timeout(10):
            while True:
                if proc.returncode is not None:
                    pytest.fail("HTTP server exited before listening")
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                except OSError:
                    await asyncio.sleep(0.05)
                else:
                    writer.close()
                    await writer.wait_closed()
                    break
        async with Client(f"http://127.0.0.1:{port}/mcp") as client:
            assert len((await client.list_tools()).tools) == 11
            result = await client.call_tool("plenticore_status", {})
            assert not result.is_error
            assert result.structured_content["session"]["authenticated"] is True
    finally:
        if proc.returncode is None:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 5)
        except TimeoutError:
            proc.kill()
            await proc.wait()


async def test_float_readback_numeric_equivalence(tools, inverter):
    inverter.metadata.append({"id": "Float", "type": "double", "access": "readwrite"})
    inverter.setting_values["Float"] = "10.0"
    inverter.ignore_writes = True
    result = await tools.update_settings("devices:local", {"Float": "10"}, dry_run=False)
    assert result["verification"] == "matched"
