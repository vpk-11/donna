import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastmcp import FastMCP

from mcp.tools.admin import admin_mcp
from mcp.tools.clients import clients_mcp
from mcp.tools.scheduling import scheduling_mcp

mcp = FastMCP("donna")
mcp.mount("clients", clients_mcp)
mcp.mount("scheduling", scheduling_mcp)
mcp.mount("admin", admin_mcp)

if __name__ == "__main__":
    mcp.run()
