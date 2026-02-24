"""Entry point for the Computer Vision MCP plugin.

Run with: python -m src
"""

from src.dpi import init_dpi_awareness

# Initialize DPI awareness BEFORE any Win32 API calls
init_dpi_awareness()

# Import server (which auto-registers all tools) and run
from src.server import mcp

mcp.run(transport="stdio")
