---
name: council-setup
description: Install The Council plugin dependencies. Run this after installing the plugin.
---

# Council Setup

## Step 1: Check uv
Run: `uv --version`
If not found, tell the user to install uv:
- macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

## Step 2: Install dependencies
Run: `uv sync --directory "${CLAUDE_PLUGIN_ROOT}"`

## Step 3: Verify MCP server can import
Run: `uv run --directory "${CLAUDE_PLUGIN_ROOT}" python -c "from src.server import mcp; print('MCP OK: ' + str(len(mcp._tool_manager.list_tools())) + ' tools')"`

## Step 4: Check agent teams
Check if agent teams are enabled: look for `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` in the environment or VS Code settings. If not set, tell the user:
- "Agent teams are required. Add `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` to your environment variables or VS Code settings."

## Step 5: Done
Tell the user:
- "Council plugin installed. Restart Claude Code to connect the MCP server."
- "Then run `/council:init` in any project to set up consultation."
