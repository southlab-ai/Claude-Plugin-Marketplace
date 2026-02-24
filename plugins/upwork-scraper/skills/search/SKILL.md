---
name: search
description: Search Upwork jobs with keywords and filters. Use when the user wants to find specific types of freelance jobs, mentions "search jobs", "find work", "look for jobs on Upwork".
---

# Search Upwork Jobs

Search for Upwork jobs using the MCP tools with the user's query.

## How this plugin works

This plugin provides MCP tools (prefixed `mcp__upwork-scraper__*` or called as `tool_*` below) that control a Camoufox browser for scraping Upwork. The plugin works from **any directory**.

**If MCP tools are NOT available** (you don't see `mcp__upwork-scraper__*` in your tools): the MCP server failed to start, likely because dependencies aren't installed. Tell the user:
> The plugin's MCP server is not connected. Run `/upwork-scraper:setup` to install dependencies, then restart Claude Code.

Do NOT try workarounds (Chrome extension, curl, direct DB access). Only the MCP tools work.

## Steps

1. **Check session**: Call `tool_session_status`. If not active, call `tool_start_session` and guide the user through login.

2. **Parse the query**: The user's input is in $ARGUMENTS. Extract:
   - The main search query (keywords)
   - Any mentioned filters (experience level, budget range, job type)
   - If no filters specified, use sensible defaults

3. **Search**: Call `tool_search_jobs` with the parsed parameters.

4. **Present results** as a clean numbered list showing:
   - Job title (bold)
   - Budget or hourly rate
   - Experience level
   - Key skills
   - Client rating and spending history
   - URL

5. **Offer to refine**: Ask if they want to:
   - Filter further (by budget, experience, etc.)
   - See full details on a specific job
   - Run a different search
   - Analyze what these jobs require
