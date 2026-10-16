"""Small MCP client used by the EventPilot LangGraph workflow."""

import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "http://127.0.0.1:8000/mcp"


async def call_planning_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    # Imported lazily after the planning request initializes Langfuse tracing.
    from langfuse import get_client

    with get_client().start_as_current_observation(
        as_type="tool",
        name=f"mcp.{name}",
        input=arguments,
        metadata={"mcp_server": "eventpilot", "mcp_url": MCP_URL},
    ) as observation:
        try:
            async with streamablehttp_client(MCP_URL) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
            if result.isError or not result.content:
                raise RuntimeError(f"MCP tool {name} did not return a usable result")
            payload = json.loads(result.content[0].text)
            observation.update(output=payload)
            return payload
        except Exception as error:
            observation.update(level="ERROR", status_message=str(error))
            raise
