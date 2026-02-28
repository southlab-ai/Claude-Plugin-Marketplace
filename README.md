# Southlab AI Plugin Marketplace

Claude Code plugin marketplace by [Southlab AI](https://github.com/southlab-ai).

## Available Plugins

| Plugin | Description | Version | Category |
|--------|-------------|---------|----------|
| **upwork-scraper** | Scrape Upwork jobs, analyze market demand, write proposals, optimize rates, and build portfolios. 5 slash commands + 5 AI agents. | 0.2.0 | Freelance |
| **the-council** | Catch blind spots in architecture decisions with multi-perspective analysis. 4 auto-routed modes, configurable roles, `/council:build` pipeline, `/council:value` analysis, memory attribution, progressive hints. | 3.2.0 | Productivity |
| **computer-vision** | Desktop computer vision and input control for Windows. 28 tools: screenshots, click, type, scroll, OCR, element finder, text extraction, UI trees, app-specific adapters, action verification, and 9 sandbox tools for parallel automation (Claude works in isolated Windows Sandbox while you keep working). | 2.0.0 | Utilities |

## Installation

### 1. Add the marketplace

Inside Claude Code:

```
/plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
```

### 2. Install a plugin

```
/plugin install upwork-scraper@southlab-marketplace
/plugin install the-council@southlab-marketplace
/plugin install computer-vision@southlab-marketplace
```

### 3. Restart Claude Code

Close and reopen Claude Code for the MCP server to connect.

### 4. Run setup

Each plugin has a setup command:

```
/upwork-scraper:setup
/council:setup
/cv-setup
```

## Commands

### Upwork Scraper

| Command | Description |
|---------|-------------|
| `/upwork-scraper:setup` | Install dependencies |
| `/upwork-scraper:best-matches` | Fetch personalized Best Matches |
| `/upwork-scraper:search <query>` | Search jobs with filters |
| `/upwork-scraper:analyze <skill>` | Analyze market demand |
| `/upwork-scraper:portfolio <skills>` | Get portfolio project ideas |

### The Council (v3.2.0)

| Command | Description |
|---------|-------------|
| `/council:setup` | Install dependencies (auto-offers init) |
| `/council:init` | Initialize `.council/` in your project |
| `/council:consult <goal>` | Multi-perspective consultation (auto-routed: default, debate, plan, reflect) |
| `/council:value <goal>` | Value-realization analysis: scores 4 dimensions (clarity, timeline, perception, discovery) |
| `/council:build <goal>` | Full build pipeline: PRD + tech deck + backlog + feature gate + implementation |
| `/council:status` | View decisions, memory health, staleness warnings, compaction recommendations |
| `/council:maintain` | Compact memory using the curator agent |
| `/council:update` | Migrate council data after a plugin update |
| `/council:reset` | Clear session data (add `--all` to also clear memory) |

### Computer Vision (v2.0.0)

| Tool | Description |
|------|-------------|
| `cv_list_windows` | List all visible windows with HWND, title, process, rect |
| `cv_screenshot_window` | Capture a window |
| `cv_screenshot_desktop` | Capture the desktop |
| `cv_screenshot_region` | Capture a region |
| `cv_focus_window` | Bring a window to the foreground |
| `cv_mouse_click` | Click at screen coordinates |
| `cv_type_text` | Type text with optional hwnd for atomic focus+type |
| `cv_send_keys` | Send key combinations |
| `cv_scroll` | Scroll a window |
| `cv_move_window` | Move/resize a window |
| `cv_ocr` | Extract text with bounding boxes and confidence |
| `cv_find` | Find elements by natural language (UIA + OCR) |
| `cv_get_text` | Extract all visible text |
| `cv_list_monitors` | List monitors with resolution and DPI |
| `cv_read_ui` | Read the UI accessibility tree |
| `cv_wait_for_window` | Wait for a window to appear |
| `cv_wait` | Simple delay (max 30 seconds) |
| `cv_sandbox_start` | Launch Windows Sandbox for isolated automation |
| `cv_sandbox_stop` | Stop the sandbox session |
| `cv_sandbox_click` | Click inside sandbox (doesn't move your cursor) |
| `cv_sandbox_type` | Type inside sandbox (doesn't affect your keyboard) |
| `cv_sandbox_screenshot` | Capture screenshot from sandbox |
| `cv_sandbox_scene` | Get UI element tree from sandbox |
| `cv_sandbox_batch` | Execute multiple actions in one call (reduces latency) |
| `cv_sandbox_check` | Check if sandbox is available on your system |
| `cv_session_status` | Get sandbox session health and action history |

| Command | Description |
|---------|-------------|
| `/cv-setup` | Verify setup and dependencies |
| `/cv-help` | Usage guide and examples |

## Updating

```
/plugin marketplace update southlab-marketplace
```

## Team Configuration

Add to your project's `.claude/settings.json` to auto-prompt teammates:

```json
{
  "extraKnownMarketplaces": {
    "southlab-marketplace": {
      "source": {
        "source": "github",
        "repo": "southlab-ai/Claude-Plugin-Marketplace"
      }
    }
  },
  "enabledPlugins": {
    "the-council@southlab-marketplace": true,
    "computer-vision@southlab-marketplace": true
  }
}
```

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) v1.0.33+
- Agent teams enabled: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Windows 10 21H2+ or Windows 11 (for computer-vision)

## Repository Structure

This is a monorepo. All plugins live as subdirectories under `plugins/`:

```
Claude-Plugin-Marketplace/
├── .claude-plugin/
│   └── marketplace.json      # Plugin registry
├── plugins/
│   ├── upwork-scraper/       # Upwork scraping & market analysis
│   ├── the-council/          # Multi-agent consultation
│   └── computer-vision/      # Desktop vision & automation
└── README.md
```

Updating a plugin and the marketplace is a single commit.

## License

MIT
