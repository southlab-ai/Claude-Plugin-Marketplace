"""Configuration for The Council plugin."""

import os
from pathlib import Path


def get_plugin_root() -> str:
    """Get the plugin root directory."""
    return os.environ.get(
        "CLAUDE_PLUGIN_ROOT",
        str(Path(__file__).parent.parent),
    )
