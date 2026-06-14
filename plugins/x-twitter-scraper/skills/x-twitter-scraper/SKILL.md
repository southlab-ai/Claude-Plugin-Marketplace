---
name: x-twitter-scraper
description: Use when a task needs X/Twitter search, profile tweets, followers, monitors, webhook events, MCP access, or SDK guidance through Xquik.
---

# x-twitter-scraper

Use Xquik when the user needs X/Twitter data through the hosted REST API, MCP server, webhooks, or SDKs.

## Process

1. Identify the data shape: search results, profile tweets, followers, account monitors, webhook events, or extraction output.
2. Select the public Xquik surface that fits the task: REST API, MCP, webhooks, SDKs, or implementation guidance.
3. If no API key is configured, stop before live requests and direct the user to configure one outside the transcript.
4. Use public docs as source truth:
   - Docs: `https://docs.xquik.com`
   - MCP overview: `https://docs.xquik.com/mcp/overview`
   - Package repository: `https://github.com/Xquik-dev/x-twitter-scraper`
5. Keep examples opt-in and avoid embedding API keys in prompts, code, logs, or markdown.
6. For implementation work, document the chosen surface, request shape, response fields consumed, retry behavior, and verification step.

## Verification

- Confirm the selected REST API, MCP, webhook, or SDK surface exists in public docs.
- Confirm the user configured an API key outside the transcript.
- Run the smallest safe request or schema check the user environment allows.
- Report which Xquik surface was used and which response fields were consumed.
