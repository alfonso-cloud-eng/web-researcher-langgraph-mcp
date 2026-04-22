"""
Starts the MCP browser server as a subprocess over STDIO and returns
the LangChain-compatible tool list.
"""
import os
from langchain_mcp_adapters.client import MultiServerMCPClient


def get_mcp_client() -> MultiServerMCPClient:
    server_path = os.getenv("MCP_SERVER_PATH", "./mcp_browser_server/dist/index.js")
    abs_path = os.path.abspath(server_path)

    client = MultiServerMCPClient(
        {
            "browser": {
                "command": "node",
                "args": [abs_path],
                "transport": "stdio",
            }
        }
    )
    return client
