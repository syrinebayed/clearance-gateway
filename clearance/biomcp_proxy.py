"""MCP client that forwards allowed calls to an unmodified `biomcp serve` process.

One short-lived session per call: slower (about a second) but has no cross-task lifecycle bugs.
"""
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ALLOWED_UPSTREAM_TOOLS = ("search", "get")


class BioMCPProxy:
    def __init__(self, command: str) -> None:
        self.params = StdioServerParameters(command=command, args=["serve"])

    async def call(self, tool: str, arguments: dict) -> tuple[str, bool]:
        """Call BioMCP `search` or `get`. Returns (text, is_error)."""
        if tool not in ALLOWED_UPSTREAM_TOOLS:
            return f"upstream tool '{tool}' is not proxied", True
        async with stdio_client(self.params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
        text = "".join(getattr(part, "text", "") for part in result.content)
        return text, bool(getattr(result, "is_error", False))

    async def close(self) -> None:
        """Nothing to close: each call owns its own session."""
