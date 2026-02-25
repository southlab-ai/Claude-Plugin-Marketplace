"""Data collector for Polymarket APIs.

Fetches leaderboard, trades, positions, and market data.
All public endpoints — no auth required.
"""

import json
import time
import sqlite3
from datetime import datetime, timezone

import httpx

from explorer.db import get_connection, init_db

BASE_DATA = "https://data-api.polymarket.com"
BASE_GAMMA = "https://gamma-api.polymarket.com"
BASE_CLOB = "https://clob.polymarket.com"

# Simple rate limiter: min seconds between requests
MIN_INTERVAL = 0.35  # ~170 req/min, well under limits
_last_request = 0.0


def _throttled_get(url: str, params: dict | None = None, timeout: float = 30.0) -> dict | list:
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_request = time.monotonic()

    resp = httpx.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

CATEGORIES = ["OVERALL", "POLITICS", "SPORTS", "CRYPTO", "CULTURE", "ECONOMICS", "TECH", "FINANCE"]
TIME_PERIODS = ["DAY", "WEEK", "MONTH", "ALL"]


def fetch_leaderboard(
    category: str = "OVERALL",
    time_period: str = "ALL",
    order_by: str = "PNL",
    limit: int = 50,
) -> list[dict]:
    """Fetch leaderboard page. Max 50 per call."""
    results = []
    offset = 0
    while offset < limit:
        page_size = min(50, limit - offset)
        data = _throttled_get(f"{BASE_DATA}/v1/leaderboard", {
            "category": category,
            "timePeriod": time_period,
            "orderBy": order_by,
            "limit": page_size,
            "offset": offset,
        })
        if not data:
            break
        results.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
    return results


def collect_leaderboard(categories: list[str] | None = None, time_periods: list[str] | None = None, limit: int = 50):
    """Fetch leaderboard across categories/periods and store in DB."""
    categories = categories or ["OVERALL"]
    time_periods = time_periods or ["ALL"]
    conn = get_connection()
    total_wallets = 0
    total_snapshots = 0

    for cat in categories:
        for period in time_periods:
            print(f"  Fetching leaderboard: {cat} / {period} ...")
            entries = fetch_leaderboard(category=cat, time_period=period, limit=limit)
            for e in entries:
                wallet = e.get("proxyWallet", "")
                if not wallet:
                    continue
                # Upsert wallet
                conn.execute("""
                    INSERT INTO wallets (proxy_wallet, username, profile_image, x_username, verified, source)
                    VALUES (?, ?, ?, ?, ?, 'leaderboard')
                    ON CONFLICT(proxy_wallet) DO UPDATE SET
                        username = COALESCE(excluded.username, wallets.username),
                        profile_image = COALESCE(excluded.profile_image, wallets.profile_image),
                        x_username = COALESCE(excluded.x_username, wallets.x_username),
                        verified = excluded.verified,
                        updated_at = datetime('now')
                """, (wallet, e.get("userName"), e.get("profileImage"), e.get("xUsername"), int(e.get("verifiedBadge", False))))
                total_wallets += 1

                # Snapshot
                conn.execute("""
                    INSERT INTO leaderboard_snapshots (proxy_wallet, rank, pnl, volume, category, time_period)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (wallet, e.get("rank"), e.get("pnl"), e.get("vol"), cat, period))
                total_snapshots += 1

    conn.commit()
    conn.close()
    print(f"  Leaderboard done: {total_wallets} wallet upserts, {total_snapshots} snapshots")
    return total_snapshots


# ---------------------------------------------------------------------------
# Trades per wallet
# ---------------------------------------------------------------------------

def fetch_trades(wallet: str, limit: int = 500) -> list[dict]:
    """Fetch trade history for a wallet. Paginates up to `limit`."""
    results = []
    offset = 0
    while offset < limit:
        page_size = min(500, limit - offset)
        data = _throttled_get(f"{BASE_DATA}/trades", {
            "user": wallet,
            "limit": page_size,
            "offset": offset,
        })
        if not data:
            break
        results.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
    return results


def collect_trades_for_wallet(wallet: str, limit: int = 500) -> int:
    """Fetch and store trades for a single wallet."""
    trades = fetch_trades(wallet, limit=limit)
    if not trades:
        return 0

    conn = get_connection()
    stored = 0
    for t in trades:
        tx_hash = t.get("transactionHash")
        if not tx_hash:
            continue
        try:
            conn.execute("""
                INSERT OR IGNORE INTO trades
                (proxy_wallet, side, asset, condition_id, size, price, timestamp,
                 title, slug, event_slug, outcome, outcome_index, tx_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wallet, t.get("side"), t.get("asset"), t.get("conditionId"),
                t.get("size"), t.get("price"), t.get("timestamp"),
                t.get("title"), t.get("slug"), t.get("eventSlug"),
                t.get("outcome"), t.get("outcomeIndex"), tx_hash,
            ))
            stored += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return stored


def collect_trades_for_all_wallets(limit_per_wallet: int = 500):
    """Fetch trades for every known wallet."""
    conn = get_connection()
    wallets = [r["proxy_wallet"] for r in conn.execute("SELECT proxy_wallet FROM wallets").fetchall()]
    conn.close()

    print(f"  Collecting trades for {len(wallets)} wallets ...")
    total = 0
    for i, w in enumerate(wallets):
        n = collect_trades_for_wallet(w, limit=limit_per_wallet)
        total += n
        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(wallets)}] {total} trades so far")
    print(f"  Trades done: {total} total")
    return total


# ---------------------------------------------------------------------------
# Positions per wallet
# ---------------------------------------------------------------------------

def fetch_positions(wallet: str, limit: int = 500) -> list[dict]:
    """Fetch current positions for a wallet."""
    results = []
    offset = 0
    while offset < limit:
        page_size = min(500, limit - offset)
        data = _throttled_get(f"{BASE_DATA}/positions", {
            "user": wallet,
            "limit": page_size,
            "offset": offset,
            "sizeThreshold": 0,
        })
        if not data:
            break
        results.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
    return results


def collect_positions_for_wallet(wallet: str) -> int:
    """Fetch and store current positions snapshot for a wallet."""
    positions = fetch_positions(wallet)
    if not positions:
        return 0

    conn = get_connection()
    stored = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for p in positions:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO positions
                (proxy_wallet, asset, condition_id, size, avg_price, initial_value,
                 current_value, cash_pnl, percent_pnl, realized_pnl, cur_price,
                 redeemable, title, slug, event_slug, outcome, outcome_index,
                 end_date, captured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wallet, p.get("asset"), p.get("conditionId"),
                p.get("size"), p.get("avgPrice"), p.get("initialValue"),
                p.get("currentValue"), p.get("cashPnl"), p.get("percentPnl"),
                p.get("realizedPnl"), p.get("curPrice"),
                int(p.get("redeemable", False)),
                p.get("title"), p.get("slug"), p.get("eventSlug"),
                p.get("outcome"), p.get("outcomeIndex"),
                p.get("endDate"), now,
            ))
            stored += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()
    return stored


def collect_positions_for_all_wallets():
    """Snapshot positions for all known wallets."""
    conn = get_connection()
    wallets = [r["proxy_wallet"] for r in conn.execute("SELECT proxy_wallet FROM wallets").fetchall()]
    conn.close()

    print(f"  Collecting positions for {len(wallets)} wallets ...")
    total = 0
    for i, w in enumerate(wallets):
        n = collect_positions_for_wallet(w)
        total += n
        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(wallets)}] {total} positions so far")
    print(f"  Positions done: {total} total")
    return total


# ---------------------------------------------------------------------------
# Market metadata
# ---------------------------------------------------------------------------

def fetch_markets(limit: int = 200, active_only: bool = True) -> list[dict]:
    """Fetch market metadata from Gamma API."""
    results = []
    offset = 0
    while offset < limit:
        page_size = min(100, limit - offset)
        params = {"limit": page_size, "offset": offset, "order": "volume", "ascending": "false"}
        if active_only:
            params["active"] = "true"
        data = _throttled_get(f"{BASE_GAMMA}/markets", params)
        if not data:
            break
        results.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
    return results


def collect_markets(limit: int = 200):
    """Fetch and store market metadata."""
    markets = fetch_markets(limit=limit)
    conn = get_connection()
    stored = 0
    for m in markets:
        cid = m.get("conditionId")
        if not cid:
            continue
        outcomes = json.dumps(m.get("outcomes", []))
        conn.execute("""
            INSERT INTO markets (condition_id, question_id, title, slug, event_slug,
                                 outcomes, end_date, active, volume, liquidity, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(condition_id) DO UPDATE SET
                title = excluded.title,
                active = excluded.active,
                volume = excluded.volume,
                liquidity = excluded.liquidity,
                updated_at = datetime('now')
        """, (
            cid, m.get("questionID"), m.get("question", m.get("title")),
            m.get("slug"), m.get("eventSlug"), outcomes,
            m.get("endDate"), int(m.get("active", True)),
            m.get("volume"), m.get("liquidity"),
        ))
        stored += 1
    conn.commit()
    conn.close()
    print(f"  Markets done: {stored} upserted")
    return stored


# ---------------------------------------------------------------------------
# Top holders per market (wallet discovery)
# ---------------------------------------------------------------------------

def collect_holders_for_market(condition_id: str, limit: int = 100) -> int:
    """Fetch top holders for a market and discover new wallets."""
    data = _throttled_get(f"{BASE_DATA}/holders", {"market": condition_id, "limit": limit})
    if not data:
        return 0

    conn = get_connection()
    discovered = 0
    # data is a list of token objects, each with a "holders" array
    for token_group in data:
        holders = token_group.get("holders", []) if isinstance(token_group, dict) else []
        for h in holders:
            wallet = h.get("proxyWallet", "")
            if not wallet:
                continue
            conn.execute("""
                INSERT INTO wallets (proxy_wallet, username, profile_image, source)
                VALUES (?, ?, ?, 'holders')
                ON CONFLICT(proxy_wallet) DO UPDATE SET
                    updated_at = datetime('now')
            """, (wallet, h.get("pseudonym") or h.get("name"), h.get("profileImage")))
            discovered += 1
    conn.commit()
    conn.close()
    return discovered


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_full_collection(
    leaderboard_categories: list[str] | None = None,
    leaderboard_periods: list[str] | None = None,
    leaderboard_limit: int = 50,
    trades_per_wallet: int = 500,
    market_limit: int = 200,
    discover_holders: bool = True,
    holders_top_n_markets: int = 20,
):
    """Run the full data collection pipeline."""
    print("=" * 60)
    print("POLYMARKET DATA COLLECTION")
    print("=" * 60)

    init_db()

    # 1. Markets
    print("\n[1/5] Fetching markets ...")
    collect_markets(limit=market_limit)

    # 2. Leaderboard
    print("\n[2/5] Fetching leaderboard ...")
    collect_leaderboard(
        categories=leaderboard_categories or ["OVERALL"],
        time_periods=leaderboard_periods or ["ALL", "MONTH"],
        limit=leaderboard_limit,
    )

    # 3. Discover wallets from top market holders
    if discover_holders:
        print(f"\n[3/5] Discovering wallets from top {holders_top_n_markets} markets ...")
        conn = get_connection()
        top_markets = conn.execute(
            "SELECT condition_id FROM markets ORDER BY volume DESC LIMIT ?",
            (holders_top_n_markets,)
        ).fetchall()
        conn.close()
        for m in top_markets:
            collect_holders_for_market(m["condition_id"])
    else:
        print("\n[3/5] Skipping holder discovery")

    # 4. Trades
    print("\n[4/5] Fetching trades ...")
    collect_trades_for_all_wallets(limit_per_wallet=trades_per_wallet)

    # 5. Positions
    print("\n[5/5] Fetching positions ...")
    collect_positions_for_all_wallets()

    # Summary
    conn = get_connection()
    stats = {
        "wallets": conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0],
        "trades": conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0],
        "positions": conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0],
        "markets": conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0],
        "snapshots": conn.execute("SELECT COUNT(*) FROM leaderboard_snapshots").fetchone()[0],
    }
    conn.close()

    print("\n" + "=" * 60)
    print("COLLECTION COMPLETE")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    print("=" * 60)
    return stats


if __name__ == "__main__":
    run_full_collection()
