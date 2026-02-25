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

## Step 5: Auto-initialize (if in a project)

Check if the current working directory looks like a project (has a `.git/` directory, `package.json`, `pyproject.toml`, `Cargo.toml`, or similar). If yes, AND `.council/` does not already exist:
- Ask: "Initialize the council in this project now? (y/n)"
- If yes: call `council_memory_init` with the current project directory.
- If no: tell them they can run `/council:init` later in any project.

## Step 6: Done
Tell the user:
- "Setup complete. Restart Claude Code to connect the MCP server."
- "Then run `/council:consult <question>` to catch blind spots in your next decision."
- If auto-init was done: "Council already initialized here — you can consult right after restart."
