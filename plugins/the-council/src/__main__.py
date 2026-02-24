"""Entry point for `python -m src`."""
from .server import mcp

mcp.run(transport="stdio")
