# Upwork Scraper - Claude Code Plugin

A Claude Code plugin that scrapes Upwork jobs, analyzes market demand, and helps freelancers build winning portfolios.

Since Upwork has no public job search API (GraphQL API doesn't support it, RSS feeds were discontinued Aug 2024), this plugin uses Camoufox browser automation to scrape all listings directly. Cloudflare blocks non-browser HTTP requests (403), so all page fetching goes through the browser.

## Features

- **One-Command Setup** - `/upwork-scraper:setup` installs everything automatically
- **Best Matches** - Fetch your personalized Upwork job recommendations
- **Job Search** - Search with keywords, filters, and boolean queries
- **Market Analysis** - Understand skill demand, budget ranges, and trends
- **Portfolio Suggestions** - Get data-driven project ideas to showcase your skills
- **5 Specialized Agents** - Proposal writing, job evaluation, rate optimization, profile review, and portfolio design

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) v1.0.33+
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) and Firefox are installed automatically by `/upwork-scraper:setup`

## Quick Start

### 1. Install the plugin

Inside Claude Code:

```
/plugin marketplace add MasterMind-SL/Upwork-Plugin-Claude
/plugin install upwork-scraper@upwork-plugin-claude
```

### 2. Restart Claude Code

Close and reopen Claude Code. You can open it from **any directory** — the plugin loads globally regardless of where you are.

### 3. Install dependencies

```
/upwork-scraper:setup
```

This automatically installs `uv` (if needed), Python packages, and Firefox browser. When it finishes, **restart Claude Code again** so the MCP server can connect.

### 4. Start using it

```
/upwork-scraper:best-matches 20
```

On the first scraping command, a browser window will open. Log in to Upwork and solve any CAPTCHAs. After that, your session is saved for future use.

> **Note:** The MCP server won't connect until dependencies are installed. If skills seem broken (Claude tries wrong approaches), it means step 3 wasn't completed. Run `/upwork-scraper:setup` and restart.

## Installation Options

### Option 1: Marketplace (recommended)

See [Quick Start](#quick-start) above.

### Option 2: From source (for development)

```bash
# Clone the repository
git clone https://github.com/MasterMind-SL/Upwork-Plugin-Claude
cd Upwork-Plugin-Claude

# Install dependencies
uv sync
uv run playwright install firefox

# Create local config (optional)
cp .env.example .env

# Launch Claude Code with the plugin loaded
claude --plugin-dir .
```

### Option 3: Team marketplace

Add this to your project's `.claude/settings.json` so team members get prompted to install it:

```json
{
  "extraKnownMarketplaces": {
    "upwork-plugin-claude": {
      "source": {
        "source": "github",
        "repo": "MasterMind-SL/Upwork-Plugin-Claude"
      }
    }
  },
  "enabledPlugins": {
    "upwork-scraper@upwork-plugin-claude": true
  }
}
```

## Usage

Once loaded, you get 5 slash commands:

| Command | Description |
|---------|-------------|
| `/upwork-scraper:setup` | Install dependencies (uv, packages, browser) |
| `/upwork-scraper:best-matches` | Fetch your personalized Best Matches |
| `/upwork-scraper:search <query>` | Search jobs (e.g., `/upwork-scraper:search python fastapi`) |
| `/upwork-scraper:analyze <skill>` | Analyze market demand for a skill |
| `/upwork-scraper:portfolio <skills>` | Get portfolio project ideas for your skills |

### Example workflow

```
> /upwork-scraper:best-matches 30

Found 30 Best Matches:
1. **AI Agent Developer** - $50-80/hr | Expert | Python, LangChain...

> /upwork-scraper:analyze python

Top skills in demand: Python (85%), FastAPI (42%), Django (38%)...

> /upwork-scraper:portfolio python,fastapi,react

Project 1: AI-Powered API Gateway...
```

## Agents

The plugin includes 5 specialized agents that Claude invokes automatically:

| Agent | What it does |
|-------|-------------|
| `portfolio-designer` | Designs open-source portfolio projects from market data |
| `proposal-writer` | Crafts tailored proposals for specific job postings |
| `job-evaluator` | Evaluates jobs for red flags, fit, and ROI before applying |
| `rate-optimizer` | Analyzes market rates and recommends optimal pricing |
| `profile-reviewer` | Reviews your Upwork profile against market demand |

## How It Works

```
Claude Code <--STDIO/JSON-RPC--> MCP Server (src/server.py)
                                      |
                                 HTTP :8024
                                      |
                                 Session Manager
                                      |
                                 Camoufox browser
                                 (login + scraping)
```

The plugin runs as an **MCP server** that communicates with Claude Code via STDIO. When loaded, it auto-starts a Session Manager on `localhost:8024` that controls a Camoufox browser. All scraping happens through the browser — Cloudflare blocks non-browser requests.

The plugin provides 11 MCP tools that the skills and agents use. You don't call these tools directly — the skills and agents handle that for you.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Skills run but Claude tries wrong approaches (Chrome extension, curl, etc.) | MCP server not connected — dependencies not installed | Run `/upwork-scraper:setup`, then restart Claude Code |
| `/upwork-scraper:setup` can't find plugin directory | Plugin not installed or cache path changed | Re-install: `/plugin install upwork-scraper@upwork-plugin-claude` |
| Browser opens but scraping returns 0 jobs | Session expired or Cloudflare block | Log in again in the browser window, solve CAPTCHAs |
| "Permission to use Bash has been denied" during setup | Claude Code in restrictive permission mode | Allow Bash execution when prompted, or run setup manually (see below) |

### Manual setup (if `/upwork-scraper:setup` can't run)

Find the plugin directory and run:

```bash
# Default marketplace location:
cd ~/.claude/plugins/cache/upwork-plugin-claude/upwork-scraper/*/

# Install
uv sync
uv run playwright install firefox
cp .env.example .env
```

Then restart Claude Code.

## Configuration

Environment variables (in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_MANAGER_HOST` | `127.0.0.1` | Session Manager bind address |
| `SESSION_MANAGER_PORT` | `8024` | Session Manager port |
| `DATA_DIR` | `./data` | SQLite DB and browser profile storage |
| `BROWSER_HEADLESS` | `false` | Must be `false` for CAPTCHA solving |
| `BROWSER_TIMEOUT` | `30000` | Browser navigation timeout (ms) |

## Development

```bash
# Run tests
uv run pytest

# Run Session Manager standalone
uv run python -m src.session_manager

# Run MCP Server standalone (STDIO)
uv run python -m src.server
```

## License

MIT
