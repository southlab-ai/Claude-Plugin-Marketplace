"""CLI entry point for data collection.

Usage:
    python -m explorer.collect_cli                    # Quick run (OVERALL, 50 traders)
    python -m explorer.collect_cli --full             # All categories, 50 traders each
    python -m explorer.collect_cli --categories OVERALL POLITICS --limit 30
    python -m explorer.collect_cli --no-trades        # Leaderboard + markets only (fast)
"""

import argparse
import sys
import time

from explorer.collector import (
    CATEGORIES,
    TIME_PERIODS,
    collect_leaderboard,
    collect_markets,
    collect_holders_for_market,
    collect_trades_for_all_wallets,
    collect_positions_for_all_wallets,
    run_full_collection,
)
from explorer.db import init_db, get_connection


def main():
    parser = argparse.ArgumentParser(description="Polymarket Data Collector")
    parser.add_argument("--full", action="store_true", help="Collect all categories and time periods")
    parser.add_argument("--categories", nargs="+", default=["OVERALL"], choices=CATEGORIES)
    parser.add_argument("--periods", nargs="+", default=["ALL", "MONTH"], choices=TIME_PERIODS)
    parser.add_argument("--limit", type=int, default=50, help="Traders per leaderboard page")
    parser.add_argument("--markets", type=int, default=200, help="Number of markets to fetch")
    parser.add_argument("--trades-limit", type=int, default=500, help="Max trades per wallet")
    parser.add_argument("--no-trades", action="store_true", help="Skip trade collection (faster)")
    parser.add_argument("--no-positions", action="store_true", help="Skip position collection")
    parser.add_argument("--no-holders", action="store_true", help="Skip holder discovery")
    parser.add_argument("--holders-markets", type=int, default=20, help="Top N markets for holder discovery")
    parser.add_argument("--stats", action="store_true", help="Show DB stats and exit")
    args = parser.parse_args()

    init_db()

    if args.stats:
        conn = get_connection()
        for table in ["wallets", "trades", "positions", "markets", "leaderboard_snapshots"]:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count:,}")
        conn.close()
        return

    if args.full:
        args.categories = CATEGORIES
        args.periods = TIME_PERIODS

    start = time.monotonic()

    print("=" * 60)
    print("POLYMARKET DATA COLLECTION")
    print(f"  Categories: {args.categories}")
    print(f"  Periods: {args.periods}")
    print(f"  Limit: {args.limit} per page")
    print("=" * 60)

    # Markets
    print("\n[1] Fetching markets ...")
    collect_markets(limit=args.markets)

    # Leaderboard
    print("\n[2] Fetching leaderboard ...")
    collect_leaderboard(categories=args.categories, time_periods=args.periods, limit=args.limit)

    # Holder discovery
    if not args.no_holders:
        print(f"\n[3] Discovering wallets from top {args.holders_markets} markets ...")
        conn = get_connection()
        top_markets = conn.execute(
            "SELECT condition_id FROM markets ORDER BY volume DESC LIMIT ?",
            (args.holders_markets,)
        ).fetchall()
        conn.close()
        for m in top_markets:
            collect_holders_for_market(m["condition_id"])
    else:
        print("\n[3] Skipping holder discovery")

    # Trades
    if not args.no_trades:
        print("\n[4] Fetching trades ...")
        collect_trades_for_all_wallets(limit_per_wallet=args.trades_limit)
    else:
        print("\n[4] Skipping trades")

    # Positions
    if not args.no_positions:
        print("\n[5] Fetching positions ...")
        collect_positions_for_all_wallets()
    else:
        print("\n[5] Skipping positions")

    elapsed = time.monotonic() - start

    # Final stats
    conn = get_connection()
    print("\n" + "=" * 60)
    print(f"DONE in {elapsed:.0f}s")
    for table in ["wallets", "trades", "positions", "markets", "leaderboard_snapshots"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,}")
    conn.close()
    print("=" * 60)


if __name__ == "__main__":
    main()
