"""FastMCP server instance and auto-registration of tool modules."""

from __future__ import annotations

import importlib
import logging
import pkgutil

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Create the shared FastMCP instance — tool modules import this and use @mcp.tool()
mcp = FastMCP("computer-vision")


def _register_tools() -> None:
    """Auto-discover and import all tool modules from src.tools package.

    Each tool module defines functions decorated with @mcp.tool() that
    reference the shared `mcp` instance from this module. Importing them
    is sufficient to register the tools.
    """
    import src.tools as tools_package

    for _importer, module_name, _is_pkg in pkgutil.iter_modules(tools_package.__path__):
        full_name = f"src.tools.{module_name}"
        try:
            importlib.import_module(full_name)
            logger.info("Registered tools from %s", full_name)
        except Exception as e:
            logger.error("Failed to load tool module %s: %s", full_name, e)


# Register all tools on import
_register_tools()
