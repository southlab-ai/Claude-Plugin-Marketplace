# Southlab AI Plugin Marketplace

Claude Code plugin marketplace by [Southlab AI](https://github.com/southlab-ai).

## Available Plugins

| Plugin | Description | Version | Category |
|--------|-------------|---------|----------|
| **agent-bridge** | Connect independent Codex or Claude chats with blocking request/reply calls while preserving the native desktop app. | 0.1.0 | Productivity |
| **upwork-scraper** | Scrape Upwork jobs, analyze market demand, write proposals, optimize rates, and build portfolios. 5 slash commands + 5 AI agents. | 0.2.0 | Freelance |
| **the-council** | Catch blind spots in architecture decisions with multi-perspective analysis. 4 auto-routed modes, configurable roles, `/council:build` pipeline, `/council:value` analysis, memory attribution, progressive hints. | 3.2.0 | Productivity |
| **computer-vision** | Desktop computer vision and input control for Windows. 24 tools: screenshots, scene analysis, human-like mouse movement, action recording, UIA-based element invocation (works on WinUI 3 apps where SendInput fails), deep UI tree search, click, drag-and-drop, type, scroll, OCR, element finder, text extraction. Background mode via PostMessage. | 2.6.0 | Utilities |
| **ultracodex** | Orchestrate a fleet of OpenAI Codex agents (GPT-5.6 sol/terra/luna) from Claude Code — multi-agent audits, reviews, migrations, and design panels with adversarial verification. Includes a `codex-agent` skill for single background workers. | 1.0.0 | Productivity |
| **claude-sentinel** | Session supervisor for Claude Code's Telegram channel — guided VPS setup, persistent sessions, crash recovery, long-term memory. 4 skills: VPS installation, Telegram configuration, access management, full gateway deployment. | 0.1.0 | Infrastructure |
| **kg-educacion** | Horacio conectado al KG educativo: currículum, OA, materiales y herramientas docentes con los permisos vigentes de la cuenta. | 3.1.0 | Education |

## Prototypes — not installable

`the-financial-council` is an unpublished research prototype. It is not listed in the marketplace and cannot be installed as a Claude Code plugin.

## Installation

### Codex Desktop

```bash
codex plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
codex plugin add agent-bridge@southlab-marketplace
codex plugin add kg-educacion@southlab-marketplace
```

Codex-compatible plugins: `agent-bridge`, `kg-educacion`. Restart Codex Desktop after installation.

### Claude Code

#### 1. Add the marketplace

Inside Claude Code:

```
/plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
```

#### 2. Install a plugin

```
/plugin install upwork-scraper@southlab-marketplace
/plugin install the-council@southlab-marketplace
/plugin install computer-vision@southlab-marketplace
/plugin install agent-bridge@southlab-marketplace
/plugin install ultracodex@southlab-marketplace
/plugin install claude-sentinel@southlab-marketplace
/plugin install kg-educacion@southlab-marketplace
```

#### 3. Restart Claude Code

Close and reopen Claude Code for the MCP server to connect.

#### 4. Run setup

Each plugin has a setup command:

```
/upwork-scraper:setup
/council:setup
/cv-setup
/kg-educacion:kg-setup
```

`agent-bridge`, `ultracodex`, and `claude-sentinel` need no setup command — invoke their skills directly.

## Commands

### Agent Bridge

Use the `agent-bridge` skill in two independent chats. The receiver registers and calls
`listen`; the sender calls `ask` and remains blocked until the receiver calls `reply`.

The default wait is one hour. The bundled MCP client timeout is 7,300 seconds, allowing
explicit waits of up to two hours.

### Ultracodex

No commands — two skills, invoked by name. Requires the [OpenAI Codex CLI](https://developers.openai.com/codex/cli) installed and authenticated (`codex login`).

| Skill | Description |
|-------|-------------|
| `ultracodex` | Fleet orchestration (max 10 concurrent Codex agents): deep audits, broad reviews, migrations, judge-panel design. Say "ultracodex" or ask for an exhaustive parallel attack on a task. |
| `codex-agent` | Spawn a single background Codex worker via `codex exec` — delegation, parallel tasks, second opinions. |

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

### Computer Vision (v2.6.0)

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

### Claude Sentinel

No commands — four skills, invoked by name:

| Skill | Description |
|-------|-------------|
| `vps-setup` | Guided step-by-step setup of Claude Code on a VPS via SSH |
| `configure` | Set up the Telegram channel — bot token, access review |
| `access` | Manage Telegram channel access — pairings, allowlists, DM/group policy |
| `deploy-sentinel` | Deploy the persistent Telegram gateway with crons and bot identity |

### KG Educación

| Command | Description |
|---------|-------------|
| `/kg-educacion:kg-setup` | Conecta el MCP de Horacio con la API key personal creada en Mi cuenta. |

| Skill | Description |
|-------|-------------|
| `planificar` | Planificar año, unidad, semana o clase con OA oficiales |
| `crear-evaluacion` | Crear evaluaciones alineadas a OA, balanceadas por demanda cognitiva |
| `buscar-recursos` | Buscar recursos y materiales docentes |
| `temas-transversales` | Temas transversales del currículum |
| `kg-overview` | Visión general del knowledge graph |

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
│   └── marketplace.json          # Plugin registry (Claude Code)
├── .agents/plugins/
│   └── marketplace.json          # Plugin registry (Codex Desktop)
├── plugins/
│   ├── agent-bridge/             # Blocking request/reply between chats
│   ├── upwork-scraper/           # Upwork scraping & market analysis
│   ├── the-council/              # Multi-agent consultation
│   ├── computer-vision/          # Desktop vision & automation (Windows)
│   ├── ultracodex/               # Codex fleet orchestration
│   ├── claude-sentinel/          # Telegram session supervisor for VPS
│   ├── kg-educacion/             # KG del Currículum Nacional de Chile
│   └── the-financial-council/    # Unpublished prototype (not installable)
└── README.md
```

Updating a plugin and the marketplace is a single commit.

## Contributing

This marketplace is **first-party only**: every plugin is built and maintained by Southlab AI. Pull requests from external vendors adding plugins that promote their own service will be closed as a policy decision. If you want to distribute your own plugins to Claude Code users, host your own marketplace repo — users can add it with `/plugin marketplace add <owner>/<repo>`.

Bug reports and fixes for existing plugins are welcome.

## License

MIT
