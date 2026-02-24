---
name: analyze
description: Analyze Upwork job market requirements from cached data. Use when the user wants to understand skill demand, market trends, budget ranges, or asks "what skills are in demand", "market analysis", "what should I learn".
---

# Analyze Upwork Job Market

Analyze cached job data to identify market trends and requirements.

## How this plugin works

This plugin provides MCP tools (prefixed `mcp__upwork-scraper__*` or called as `tool_*` below) that control a Camoufox browser for scraping Upwork. The plugin works from **any directory**.

**If MCP tools are NOT available** (you don't see `mcp__upwork-scraper__*` in your tools): the MCP server failed to start, likely because dependencies aren't installed. Tell the user:
> The plugin's MCP server is not connected. Run `/upwork-scraper:setup` to install dependencies, then restart Claude Code.

Do NOT try workarounds (Chrome extension, curl, direct DB access). Only the MCP tools work.

## Steps

1. **Check data**: Call `tool_get_scraping_stats` to see if there's enough cached data.
   - If total_jobs < 5: suggest fetching more jobs first with best-matches or search.

2. **Analyze**: Call `tool_analyze_market_requirements(skill_focus="$ARGUMENTS", top_n=20)`.

3. **Present insights** clearly:

   ### Skills in Demand
   Show top 10 skills as a ranked list with percentages.

   ### Budget Landscape
   Show budget distribution and averages.

   ### Experience Levels
   Show the breakdown (entry vs intermediate vs expert).

   ### Key Takeaways
   - What skills appear most frequently together?
   - What's the sweet spot for budget/rates?
   - What experience level has the most opportunities?

4. **Actionable advice**: Based on the analysis, suggest:
   - Skills the user should highlight
   - Skills to learn to increase competitiveness
   - Optimal rate/budget positioning
