"""SQLite database layer for Polymarket explorer data."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS wallets (
        proxy_wallet   TEXT PRIMARY KEY,
        username       TEXT,
        profile_image  TEXT,
        x_username     TEXT,
        verified       INTEGER DEFAULT 0,
        source         TEXT,  -- 'leaderboard' | 'holders' | 'manual'
        discovered_at  TEXT DEFAULT (datetime('now')),
        updated_at     TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        proxy_wallet   TEXT NOT NULL,
        rank           INTEGER,
        pnl            REAL,
        volume         REAL,
        category       TEXT DEFAULT 'OVERALL',
        time_period    TEXT,  -- 'DAY' | 'WEEK' | 'MONTH' | 'ALL'
        captured_at    TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (proxy_wallet) REFERENCES wallets(proxy_wallet)
    );

    CREATE TABLE IF NOT EXISTS trades (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        proxy_wallet   TEXT NOT NULL,
        side           TEXT,  -- 'BUY' | 'SELL'
        asset          TEXT,
        condition_id   TEXT,
        size           REAL,
        price          REAL,
        timestamp      TEXT,
        title          TEXT,
        slug           TEXT,
        event_slug     TEXT,
        outcome        TEXT,
        outcome_index  INTEGER,
        tx_hash        TEXT UNIQUE,
        FOREIGN KEY (proxy_wallet) REFERENCES wallets(proxy_wallet)
    );

    CREATE TABLE IF NOT EXISTS positions (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        proxy_wallet   TEXT NOT NULL,
        asset          TEXT,
        condition_id   TEXT,
        size           REAL,
        avg_price      REAL,
        initial_value  REAL,
        current_value  REAL,
        cash_pnl       REAL,
        percent_pnl    REAL,
        realized_pnl   REAL,
        cur_price      REAL,
        redeemable     INTEGER DEFAULT 0,
        title          TEXT,
        slug           TEXT,
        event_slug     TEXT,
        outcome        TEXT,
        outcome_index  INTEGER,
        end_date       TEXT,
        captured_at    TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (proxy_wallet) REFERENCES wallets(proxy_wallet),
        UNIQUE(proxy_wallet, condition_id, outcome_index, captured_at)
    );

    CREATE TABLE IF NOT EXISTS markets (
        condition_id   TEXT PRIMARY KEY,
        question_id    TEXT,
        title          TEXT,
        slug           TEXT,
        event_slug     TEXT,
        outcomes       TEXT,  -- JSON array
        end_date       TEXT,
        active         INTEGER DEFAULT 1,
        volume         REAL,
        liquidity      REAL,
        updated_at     TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_trades_wallet ON trades(proxy_wallet);
    CREATE INDEX IF NOT EXISTS idx_trades_condition ON trades(condition_id);
    CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
    CREATE INDEX IF NOT EXISTS idx_positions_wallet ON positions(proxy_wallet);
    CREATE INDEX IF NOT EXISTS idx_leaderboard_wallet ON leaderboard_snapshots(proxy_wallet);
    CREATE INDEX IF NOT EXISTS idx_leaderboard_period ON leaderboard_snapshots(time_period, category);
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
