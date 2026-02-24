---
name: portfolio
description: Suggest open-source portfolio projects based on Upwork market demand. Use when the user wants to build a portfolio, needs project ideas for their "carta de presentacion", or asks "what should I build", "portfolio ideas", "showcase projects".
---

# Portfolio Project Suggestions

Suggest open-source portfolio projects that align with Upwork market demand.

## How this plugin works

This plugin provides MCP tools (prefixed `mcp__upwork-scraper__*` or called as `tool_*` below) that control a Camoufox browser for scraping Upwork. The plugin works from **any directory**.

**If MCP tools are NOT available** (you don't see `mcp__upwork-scraper__*` in your tools): the MCP server failed to start, likely because dependencies aren't installed. Tell the user:
> The plugin's MCP server is not connected. Run `/upwork-scraper:setup` to install dependencies, then restart Claude Code.

Do NOT try workarounds (Chrome extension, curl, direct DB access). Only the MCP tools work.

## Steps

1. **Get market data**: Call `tool_analyze_market_requirements` to understand current demand.

2. **Generate suggestions**: Call `tool_suggest_portfolio_projects(your_skills="$ARGUMENTS", target_experience_level="intermediate", top_n=5)`.

3. **For each project, present**:

   ### Project Name
   - **What to build**: Clear description of the project
   - **Why it works**: How it maps to real job postings
   - **Tech stack**: Specific technologies to use
   - **Skills demonstrated**: What clients will see
   - **Matching jobs**: How many current jobs this prepares for
   - **Complexity**: Weekend / Week / Month estimate
   - **GitHub repo**: Suggested name and structure

4. **Prioritize** projects that:
   - Demonstrate skills for the MOST jobs
   - Are visually impressive (deployable demos)
   - Show real-world problem-solving, not toy examples
   - Can be completed in reasonable time

5. **Deployment advice**: For each project, suggest:
   - Where to deploy a live demo (Vercel, Railway, etc.)
   - How to structure the README for maximum impact
   - What screenshots/GIFs to include
