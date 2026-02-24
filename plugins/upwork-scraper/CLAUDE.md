# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Plugin Runtime Instructions

**IMPORTANT: Follow these instructions when the plugin is loaded and the user invokes any skill or asks about Upwork jobs.**

### How this plugin works

This plugin provides MCP tools (prefixed `mcp__upwork-scraper__*` or shown as `tool_*` in skills). ALL scraping, querying, and analysis goes through these MCP tools. Do NOT try to use Chrome browser extension, httpx, curl, or direct database access — only use the MCP tools provided by this plugin's server.

The plugin works from **any directory**. The user does NOT need to be inside the plugin folder. Skills and tools are available globally once the plugin is loaded.

### Detecting setup problems

When any skill is invoked, first call `tool_session_status` to check connectivity:
- **If the MCP tools are available** (you can see `mcp__upwork-scraper__*` in your tool list): the plugin is properly installed and the MCP server is running. Proceed with the skill.
- **If the MCP tools are NOT available** (tool calls fail or tools don't appear): the MCP server failed to start. This almost always means dependencies aren't installed yet. Tell the user:

```
The Upwork Scraper plugin's MCP server is not connected. This usually means
dependencies haven't been installed yet.

Run this to set everything up:
  /upwork-scraper:setup

After it finishes, restart Claude Code for the MCP server to connect.
```

Do NOT attempt workarounds like reading the database directly, using browser extensions, or running the server manually. The correct fix is always: install dependencies → restart Claude Code.

### First-time login flow

After the plugin is installed and MCP tools are available, the first scraping command will need a browser login:
1. Call `tool_start_session(headless=false)` — opens a visible Camoufox browser
2. Tell the user to log in to Upwork and solve any CAPTCHAs in the browser window
3. When the user confirms they've logged in, call `tool_check_auth` to verify
4. The session persists across restarts (cookies saved to disk)

### Available MCP tools

| Tool | Purpose |
|------|---------|
| `tool_session_status` | Check if browser session is active |
| `tool_start_session` | Launch Camoufox browser for login |
| `tool_check_auth` | Verify authentication after user logs in |
| `tool_stop_session` | Stop the browser session |
| `tool_fetch_best_matches` | Scrape personalized Best Matches |
| `tool_search_jobs` | Search jobs with keywords and filters |
| `tool_get_job_details` | Get full details for a specific job |
| `tool_list_cached_jobs` | Query locally cached jobs (no network) |
| `tool_get_scraping_stats` | Database statistics |
| `tool_analyze_market_requirements` | Aggregate market analysis |
| `tool_suggest_portfolio_projects` | Portfolio suggestions from market data |

---

## What This Is

A **Claude Code Plugin** that scrapes Upwork jobs, analyzes market demand, and suggests portfolio projects. It bundles an MCP server, 5 skills (slash commands), and 5 specialized agents.

## Architecture

```
Claude Code ←STDIO/JSON-RPC→ MCP Server (src/server.py)
                                   │
                              HTTP :8024 (auto-started via lifespan)
                                   │
                              Session Manager (src/session_manager/manager.py)
                                   │
                              Camoufox browser
                              (login/CAPTCHA/scraping)
```

The **MCP Server** (`src/server.py`) auto-starts the **Session Manager** (aiohttp on `localhost:8024`) inside its FastMCP lifespan. No separate process needed — everything starts when the plugin loads.

**All scraping uses the Camoufox browser directly.** Cloudflare ties `cf_clearance` cookies to the browser's TLS fingerprint, so httpx requests get 403 Forbidden even with transferred cookies. The browser navigates to each page, and the parser extracts data from the rendered HTML.

All stdout is reserved for MCP JSON-RPC; use stderr for logging.

## Loading the Plugin

The plugin must be explicitly loaded. Just being in the directory is NOT enough.

```bash
# Development mode (loads for current session only, use your local path)
claude --plugin-dir /path/to/upwork-scraper
```

Once loaded, skills are namespaced as `/upwork-scraper:best-matches`, `/upwork-scraper:search`, etc.

### Installing from marketplace (for end users)

Inside Claude Code:

```
/plugin marketplace add southlab-ai/Claude-Plugin-Marketplace
/plugin install upwork-scraper@southlab-marketplace
```

Then restart Claude Code and run `/upwork-scraper:setup` to set up all dependencies automatically.

Or install from a local clone:

```bash
git clone https://github.com/MasterMind-SL/Upwork-Plugin-Claude
cd Upwork-Plugin-Claude
uv sync && uv run playwright install firefox
claude --plugin-dir .
```

### Plugin structure

```
upwork-scraper/
├── .claude-plugin/
│   ├── plugin.json          ← manifest (name, version, license)
│   └── marketplace.json     ← marketplace distribution config
├── .mcp.json                ← MCP server config (uv run python -m src.server)
├── skills/                  ← 5 slash commands (SKILL.md each)
│   ├── setup/
│   ├── best-matches/
│   ├── search/
│   ├── analyze/
│   └── portfolio/
├── agents/                  ← 5 specialized agents
│   ├── portfolio-designer.md
│   ├── proposal-writer.md
│   ├── job-evaluator.md
│   ├── rate-optimizer.md
│   └── profile-reviewer.md
├── src/                     ← Python source (MCP server + Session Manager)
├── tests/
├── .env.example
├── .gitignore
├── CLAUDE.md
├── LICENSE
├── README.md
├── pyproject.toml
└── uv.lock
```

Components live at the plugin root, NOT inside `.claude-plugin/`. Only `plugin.json` goes there.

## Setup

The easiest way is to run `/upwork-scraper:setup` after loading the plugin — it handles everything automatically (installs uv, Python packages, Firefox browser, and creates `.env`).

Manual setup:

```bash
uv sync                                    # Install dependencies
uv run playwright install firefox           # Install browser for Camoufox
cp .env.example .env                        # Create local config
```

**Note:** `uv` must be in PATH. The `.mcp.json` uses `uv run --directory ${CLAUDE_PLUGIN_ROOT}` for cross-platform compatibility. If `uv` is not in PATH, see [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/).

## Running Standalone (for development/debugging)

```bash
# Session Manager only (if you need to run it separately)
uv run python -m src.session_manager

# MCP Server only (STDIO mode)
uv run python -m src.server
```

## Tests

```bash
uv run pytest                               # All tests
uv run pytest tests/test_parser.py          # Single test file
uv run pytest tests/test_parser.py -k test_name  # Single test
```

## Key Modules

| Module | Purpose |
|--------|---------|
| `src/server.py` | MCP entry point. Registers 11 `@mcp.tool()` functions. Lifespan auto-starts Session Manager. |
| `src/session_manager/browser.py` | Camoufox lifecycle: launch, login detection, page navigation, scrolling. |
| `src/session_manager/scraper.py` | Legacy httpx-based scraper (unused — Cloudflare blocks httpx with 403). Kept for reference. |
| `src/session_manager/parser.py` | Extracts job data via 3 strategies: `__NUXT_DATA__` JSON → CSS selectors → meta tags. |
| `src/session_manager/manager.py` | aiohttp HTTP service orchestrating browser + parser + SQLite. Converts tile data directly to Job objects for listings; uses browser navigation for individual job details. |
| `src/database/repository.py` | Async SQLite CRUD with smart upsert (ON CONFLICT keeps richer data via COALESCE). |
| `src/tools/` | Tool implementations grouped by domain: session, scraping, query, analysis. |
| `src/constants.py` | All Upwork URLs, CSS selectors, category UIDs, search parameter mappings. |

## Plugin Components

- **`.claude-plugin/plugin.json`**: Plugin manifest (name: `upwork-scraper`)
- **`.claude-plugin/marketplace.json`**: Marketplace config for `/plugin marketplace add` distribution
- **`.mcp.json`**: MCP server config. Uses `uv run --directory ${CLAUDE_PLUGIN_ROOT}` for cross-platform compatibility
- **`skills/`**: 5 slash commands — `setup`, `best-matches`, `search`, `analyze`, `portfolio`
- **`agents/`**: 5 subagents — `portfolio-designer`, `proposal-writer`, `job-evaluator`, `rate-optimizer`, `profile-reviewer`

## Skill YAML Frontmatter

Supported attributes in `SKILL.md` frontmatter:

| Field | Description |
|-------|-------------|
| `name` | Display name (defaults to directory name) |
| `description` | What the skill does and when to use it |
| `argument-hint` | Hint shown during autocomplete (e.g., `[query]`) |
| `disable-model-invocation` | `true` to prevent Claude from auto-invoking (manual `/name` only) |
| `user-invocable` | `false` to hide from `/` menu (Claude-only background knowledge) |
| `allowed-tools` | Tools Claude can use without permission when skill is active |
| `model` | Model to use when skill is active |
| `context` | `fork` to run in an isolated subagent context |
| `agent` | Subagent type when `context: fork` (e.g., `Explore`, `Plan`) |
| `hooks` | Hooks scoped to the skill's lifecycle |

## Important Patterns

- **Browser-only scraping**: All page fetching goes through Camoufox. Cloudflare ties `cf_clearance` cookies to the browser's TLS fingerprint (JA3 hash), so httpx gets 403 even with valid cookies. The browser navigates to pages, and the parser extracts data from rendered HTML.
- **Tile-based listings**: Best Matches and Search results are parsed as tiles from the list page HTML. Each tile provides: id, url, title, description, budget, skills, experience level, proposals, posted date. Job objects are created directly from tile data without fetching individual detail pages.
- **Browser-based job details**: When full details for a single job are requested, the browser navigates to the job page and the parser uses 3-strategy extraction: `__NUXT_DATA__` → HTML selectors → meta tags.
- **`__NUXT_DATA__` parsing**: Upwork uses Nuxt.js; job data is serialized as a flat array with index-based references in `<script id="__NUXT_DATA__">` tags
- **CAPTCHA handling**: Camoufox avoidance → Cloudflare auto-resolve (30s wait) → human-in-the-loop (visible browser window)
- **Upwork has no job search API**: Official GraphQL API doesn't support it, RSS feeds were discontinued Aug 2024. Browser scraping is the only option.

## Upwork DOM Structure (as of Feb 2025)

Upwork changes their HTML frequently. When selectors break, save `data/debug_best_matches.html` and inspect it in a browser. Current known structure:

### Best Matches / Search Results page

```
div[data-test="job-tile-list"]
  └── section.air3-card-section.air3-card-hover   ← each job tile (NOT <article>)
        ├── a[href="/jobs/Job-Title_~0ID/?referrer_url_path=..."]  ← title link (slug + ~ID)
        ├── [data-test="job-description-text"]      ← description snippet
        ├── [data-test="job-type"]                  ← "Hourly: $30-$45" or "Fixed: $500"
        ├── [data-test="contractor-tier"]           ← "Expert", "Intermediate", "Entry"
        ├── [data-test="proposals"]                 ← "50+" or "15"
        ├── [data-test="posted-on"]                 ← "2 hours ago"
        ├── [data-test="duration"]                  ← "Less than 1 month, 30+ hrs/week"
        └── a[data-test="attr-item"]               ← skill tags (one per skill)
```

### Key selector changes (historical)

| Element | Old selector | Current selector (Feb 2025) |
|---|---|---|
| Job tile wrapper | `article[data-test="JobTile"]` | `[data-test="job-tile-list"] > section` |
| Job URL pattern | `/jobs/~0ID` | `/jobs/Title-Slug_~0ID/?referrer_url_path=...` |
| Title link | `a[href*="/jobs/~"]` | `a[href*="/jobs/"][href*="~"]` |
| Budget | `[data-test="job-budget"]` | `[data-test="job-type"]` |
| Experience level | `[data-test="experience-level"]` | `[data-test="contractor-tier"]` |
| Skills | `[data-test="TokenClamp"] .air3-token` | `a[data-test="attr-item"]` |

### Job detail page (individual job)

Uses 3-strategy extraction: `__NUXT_DATA__` → HTML `data-test` selectors → `<meta>` tags. NUXT data is the most reliable source and provides 12+ structured fields directly.

## Debugging the Scraping Pipeline

All logs go to **stderr** (tagged with `[DEBUG]`, `[SCRAPE]`, `[PARSER]`, `[SCRAPER]`). When scraping returns 0 jobs, read the logs to find where it broke:

### Scrape flow and what to look for

**Best Matches / Search (tile-based):**
```
[SCRAPE] Step 1: Navigating to .../best-matches
[DEBUG]  Landed on URL: ...        ← if /login → session expired
[DEBUG]  Page title: '...'         ← if 'Cloudflare' → blocked
[DEBUG]  get_page_html: got N chars
[SCRAPE] Step 2: Scrolling...
[DEBUG]  Scroll 1: height 3200 -> 6400   ← if height never grows → page empty or JS broken
[SCRAPE] Step 3: Parsing tiles...
[PARSER] Page <title>: '...'
[PARSER] Body text preview: ...    ← if 'verify you are human' → CAPTCHA
[PARSER] Found N tiles with selector: ...   ← if 0 → Upwork changed HTML structure
[PARSER] data-test attrs on page: [...]     ← use these to write new selectors
[SCRAPE] Step 3 done: got N jobs from tiles
```

**Individual job detail (browser navigation):**
```
[DEBUG]  get_page_html: navigating to /jobs/Title_~0ID/
[DEBUG]  Landed on URL: ...
[PARSER] NUXT extracted N fields: [...]
[PARSER] HTML selectors: found N, added M new
[PARSER] Final job 'Title...' has fields: [...]
```

### Debug HTML dump

When Best Matches is scraped, the raw HTML is saved to `data/debug_best_matches.html`. Open this file in a browser to see exactly what Upwork served.

### Common failure scenarios

| Log evidence | Problem | Fix |
|---|---|---|
| URL ends with `/login` | Session expired or no cookies | Call `tool_start_session`, re-login |
| Page title = "Just a moment" or body = "Checking your browser" | Cloudflare block | CAPTCHA must be solved in visible browser |
| 0 tiles, no `data-test` attrs | Page is empty/JS didn't render | Increase scroll wait, check if Upwork changed layout |
| 0 tiles, `data-test` attrs logged | Selectors outdated | Update `tile_selectors` in `parser.py` using the logged attrs |
| NUXT fields = 0, HTML fields = 0 | Job detail page structure changed | Check `data/debug_best_matches.html`, update field maps in `parser.py` |

### Camoufox browser appearance

The browser UI may look misaligned or oddly sized — this is **normal**. Camoufox with `humanize=True` randomizes viewport, fonts, and display properties to avoid bot detection. The viewport is set to 1366x768 in `browser.py`.

## Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_MANAGER_HOST` | `127.0.0.1` | Session Manager bind address |
| `SESSION_MANAGER_PORT` | `8024` | Session Manager port |
| `DATA_DIR` | `./data` | SQLite DB, browser profile, logs |
| `BROWSER_HEADLESS` | `false` | Must be `false` for CAPTCHA solving |
| `BROWSER_TIMEOUT` | `30000` | Browser navigation timeout (ms) |

## Data Storage

All runtime data goes in `data/` (gitignored):
- `data/upwork_jobs.db` — SQLite cache of scraped jobs
- `data/browser_profile/` — Camoufox persistent cookies/fingerprint
- `data/logs/` — Application logs
- `data/debug_best_matches.html` — Last scraped Best Matches page (for debugging selectors)
