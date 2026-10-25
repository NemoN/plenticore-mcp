"""Publication checks for configuration, examples and archive boundaries."""

import asyncio
import json
import os
import sys
import tomllib
from pathlib import Path

import pytest

from scripts.check_artifacts import check_name

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.production",
        "docs/.env.backup",
        ".venv/config",
        "src/private.key",
        "src/__pycache__/module.pyc",
        "../secret",
        "/absolute",
        "unexpected.txt",
    ],
)
def test_artifact_allowlist_rejects_private_files(name):
    with pytest.raises(ValueError):
        check_name(name, wheel=False)


def test_public_metadata_and_examples():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["license"] == "MIT"
    from plenticore_mcp import __version__

    assert project["version"] == __version__
    check_name(".env.example", wheel=False)
    check_name("plenticore_mcp/server.py", wheel=True)
    json_config = json.loads((ROOT / "examples/mcp-client.json").read_text())
    toml_config = tomllib.loads((ROOT / "examples/codex.toml").read_text())
    assert json_config["mcpServers"]["plenticore"] == toml_config["mcp_servers"]["plenticore"]


async def test_default_env_file_comes_from_working_directory(inverter, tmp_path):
    (tmp_path / ".env").write_text(
        f"PLENTICORE_URL={inverter.url}\nPLENTICORE_PASSWORD=local-test-password\n"
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith("PLENTICORE_")}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "plenticore_mcp",
        "--check",
        cwd=tmp_path,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), 15)
    assert process.returncode == 0, stderr.decode()
    assert json.loads(stdout)["status"]["session"]["authenticated"] is True
    assert not any(method == "PUT" for method, _, _ in inverter.requests)
