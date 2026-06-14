---
name: setup
description: Configure Xquik docs, API key handling, and task boundaries before using X/Twitter data workflows.
---

# Xquik Setup

Use this setup skill when the user wants to connect Claude Code work to Xquik X/Twitter data workflows.

## Steps

1. Ask which surface the user wants to use: REST API, MCP, webhooks, SDKs, or implementation guidance.
2. Confirm the user has an Xquik API key configured outside the transcript before making live requests.
3. Use the public docs as source truth:
   - Docs: `https://docs.xquik.com`
   - MCP overview: `https://docs.xquik.com/mcp/overview`
   - Package repository: `https://github.com/Xquik-dev/x-twitter-scraper`
4. Keep examples minimal and opt-in. Never paste API keys into prompts, code, logs, or markdown.
5. Record the chosen surface, request shape, response fields used, and verification step.

## Done

The setup is complete when the user has selected a public Xquik surface, configured credentials outside the transcript, and identified the smallest safe verification step.
