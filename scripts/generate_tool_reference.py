"""Generate docs/tools.md from the registered MCP tools without contacting an inverter."""

import argparse
import asyncio
import json
from pathlib import Path

from mcp import Client

from plenticore_mcp.client import PlenticoreClient
from plenticore_mcp.config import Settings
from plenticore_mcp.server import build_server
from plenticore_mcp.tools import PlenticoreTools

ROOT = Path(__file__).resolve().parents[1]


async def render() -> str:
    settings = Settings(url="http://127.0.0.1:1", password="documentation-placeholder")
    server = build_server(PlenticoreTools(PlenticoreClient(settings)))
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    parts = [
        "# Tool reference\n",
        "Generated from the registered tools by `scripts/generate_tool_reference.py`.\n",
        "The examples in [configuration.md](configuration.md) explain readings and settings. "
        "IDs must come from the connected inverter.\n",
    ]
    for tool in sorted(tools, key=lambda item: item.name):
        schema = json.dumps(tool.input_schema, ensure_ascii=False, indent=2, sort_keys=True)
        access = "Read" if tool.annotations.read_only_hint else "Write (preview by default)"
        parts.extend(
            [
                f"## `{tool.name}`\n",
                f"{tool.description.strip()}\n",
                f"Access: {access}.\n",
                "Input schema:\n",
                f"```json\n{schema}\n```\n",
            ]
        )
    parts.extend(
        [
            "## Resource\n",
            "`plenticore://usage` describes measurement interpretation and the settings workflow. "
            "It can be read without contacting the inverter.\n",
        ]
    )
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = asyncio.run(render())
    target = ROOT / "docs" / "tools.md"
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            raise SystemExit("docs/tools.md is stale; regenerate the tool reference")
        print("Tool reference is current.")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print("Wrote docs/tools.md")


if __name__ == "__main__":
    main()
