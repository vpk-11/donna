from fastmcp import FastMCP

from donna_mcp.tools.clients import clients_mcp
from donna_mcp.tools.scheduling import scheduling_mcp
from donna_mcp.tools.admin import admin_mcp
from donna_mcp.tools.conversation import conversation_mcp

donna_tools = FastMCP("donna")
donna_tools.mount("clients", clients_mcp)
donna_tools.mount("scheduling", scheduling_mcp)
donna_tools.mount("admin", admin_mcp)
donna_tools.mount("conversation", conversation_mcp)

if __name__ == "__main__":
    donna_tools.run()
