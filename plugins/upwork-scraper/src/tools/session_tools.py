"""MCP tools for managing the Upwork browser session."""

from __future__ import annotations

import httpx

from ..config import SESSION_MANAGER_URL


async def _call_session_manager(method: str, path: str, json_body: dict | None = None) -> dict:
    """Make a request to the session manager HTTP service."""
    url = f"{SESSION_MANAGER_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url, json=json_body or {})

            if resp.status_code >= 400:
                data = resp.json()
                return {"error": data.get("error", f"HTTP {resp.status_code}")}
            return resp.json()

    except httpx.ConnectError:
        return {
            "error": "Session Manager is not reachable at "
            f"{SESSION_MANAGER_URL}. It should auto-start with the MCP server. "
            "If running standalone: uv run python -m src.session_manager"
        }
    except httpx.TimeoutException:
        return {"error": "Session Manager timed out. The browser may be loading."}
    except Exception as e:
        return {"error": f"Failed to connect to Session Manager: {e}"}


async def start_session(headless: bool = False) -> str:
    """Start the Upwork browser session manager.

    Launches the Camoufox anti-detection browser and attempts to restore
    a previous session from saved cookies. If no valid session exists,
    the browser window will open for manual login.

    Args:
        headless: If False (default), opens a visible browser window
                  so you can solve CAPTCHAs if needed.

    Returns:
        Session status message.
    """
    result = await _call_session_manager("POST", "/start", {"headless": headless})

    if "error" in result:
        return f"Error: {result['error']}"

    state = result.get("state", "unknown")
    message = result.get("message", "")

    if state == "active":
        return f"Session is active. {message}"
    elif state == "needs_login":
        return (
            f"Browser is open but you need to log in. {message}\n\n"
            "Please log in to Upwork in the browser window and solve any CAPTCHAs. "
            "Tell me when you're done and I'll verify the session."
        )
    elif state == "captcha_required":
        return (
            f"CAPTCHA detected: {message}\n\n"
            "Please solve the CAPTCHA in the browser window and tell me when done."
        )
    else:
        return f"Session state: {state}. {message}"


async def session_status() -> str:
    """Check if the Upwork session is currently active and authenticated.

    Returns session state, cookie info, cached job count,
    and when the last successful scrape occurred.

    Returns:
        JSON-formatted session status.
    """
    result = await _call_session_manager("GET", "/status")

    if "error" in result:
        return f"Error: {result['error']}"

    import json
    return json.dumps(result, indent=2)


async def check_auth() -> str:
    """Verify authentication after user reports login complete.

    Call this after the user says they've logged in to confirm
    the session is authenticated.

    Returns:
        Authentication status message.
    """
    result = await _call_session_manager("POST", "/check-auth")

    if "error" in result:
        return f"Error: {result['error']}"

    state = result.get("state", "unknown")
    message = result.get("message", "")

    if state == "active":
        return f"Authentication confirmed! {message}"
    elif state == "needs_login":
        return f"Not yet authenticated. {message}"
    elif state == "captcha_required":
        return f"CAPTCHA still needs solving. {message}"
    else:
        return f"State: {state}. {message}"


async def stop_session() -> str:
    """Gracefully stop the browser session manager.

    Saves cookies for future reuse and closes the browser.
    The cached job data remains available in the database.

    Returns:
        Confirmation message.
    """
    result = await _call_session_manager("POST", "/stop")

    if "error" in result:
        return f"Error: {result['error']}"

    return result.get("message", "Session stopped.")
