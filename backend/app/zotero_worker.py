"""Bundled upstream Zotero MCP tools, restricted to a read-only API surface."""

import asyncio, os, tempfile
from pathlib import Path


async def safe_server(home):
    # No discovery of other assistants' configs, user SQLite, tokens, or models.
    for key in list(os.environ):
        if key.startswith("ZOTERO_"):
            os.environ.pop(key, None)
    os.environ.update(
        HOME=str(home),
        PYTHON_DOTENV_DISABLED="1",
        ZOTERO_LOCAL="true",
        ZOTERO_BACKEND="api",
        ZOTERO_MCP_TOOLSETS="none,-semantic",
        ZOTERO_NO_CLAUDE="true",
        ZOTERO_MCP_LOCK_TIMEOUT="10",
        ZOTERO_API_KEY="",
        ZOTERO_LOCAL_API_KEY="",
        ZOTERO_LIBRARY_ID="0",
    )
    from fastmcp import FastMCP
    from zotero_mcp.server import mcp
    from app.zotero_bridge import ALLOWED

    safe = FastMCP("Campus read-only Zotero")
    for name in sorted(ALLOWED):
        safe.add_tool(await mcp.get_tool(name))
    # New server has no upstream lifespan/schema downloads/index auto-updates.
    return safe


def main():
    with tempfile.TemporaryDirectory(prefix="campus-zotero-worker-") as folder:
        server = asyncio.run(safe_server(Path(folder)))
        server.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
