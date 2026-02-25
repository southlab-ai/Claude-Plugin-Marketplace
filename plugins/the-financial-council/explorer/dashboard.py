"""Streamlit dashboard for Polymarket data exploration.

Run: streamlit run explorer/dashboard.py
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"


@st.cache_resource
def get_conn():
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


def load_df(query: str, params=()) -> pd.DataFrame:
    return pd.read_sql_query(query, get_conn(), params=params)


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="The Financial Council — Explorer", layout="wide", page_icon="📊")
st.title("The Financial Council — Polymarket Explorer")

if not DB_PATH.exists():
    st.error(f"Database not found at `{DB_PATH}`. Run the collector first:\n\n```\npython -m explorer.collect_cli\n```")
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar — Database stats
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Database")
    stats = {}
    for table in ["wallets", "trades", "positions", "markets", "leaderboard_snapshots"]:
        stats[table] = load_df(f"SELECT COUNT(*) as n FROM {table}").iloc[0]["n"]
    for k, v in stats.items():
        st.metric(k.replace("_", " ").title(), f"{v:,}")

    st.divider()
    st.caption("Data source: Polymarket public APIs")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_lb, tab_traders, tab_markets, tab_hypo, tab_deep = st.tabs([
    "Leaderboard", "Trader Analysis", "Market Intel", "Hypothesis Lab", "Deep Dive"
])


# ===== TAB 1: Leaderboard =====
with tab_lb:
    st.subheader("Leaderboard Overview")

    col1, col2 = st.columns(2)
    with col1:
        period = st.selectbox("Time Period", ["ALL", "MONTH", "WEEK", "DAY"], key="lb_period")
    with col2:
        category = st.selectbox("Category", ["OVERALL", "POLITICS", "SPORTS", "CRYPTO", "CULTURE", "ECONOMICS", "TECH", "FINANCE"], key="lb_cat")

    df_lb = load_df("""
        SELECT ls.rank, ls.pnl, ls.volume, ls.category, ls.time_period,
               w.username, w.verified, w.proxy_wallet
        FROM leaderboard_snapshots ls
        JOIN wallets w ON ls.proxy_wallet = w.proxy_wallet
        WHERE ls.time_period = ? AND ls.category = ?
        ORDER BY ls.rank ASC
    """, (period, category))

    if df_lb.empty:
        st.info("No leaderboard data for this filter. Run collector with these categories/periods.")
    else:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Traders", len(df_lb))
        with col_b:
            st.metric("Total PnL", f"${df_lb['pnl'].sum():,.0f}")
        with col_c:
            st.metric("Total Volume", f"${df_lb['volume'].sum():,.0f}")

        # PnL distribution
        fig_pnl = px.histogram(df_lb, x="pnl", nbins=30, title="PnL Distribution",
                               labels={"pnl": "Profit / Loss ($)"}, color_discrete_sequence=["#636EFA"])
        st.plotly_chart(fig_pnl, use_container_width=True)

        # PnL vs Volume scatter
        fig_scatter = px.scatter(df_lb, x="volume", y="pnl", hover_data=["username", "rank"],
                                 title="PnL vs Volume", size=df_lb["volume"].abs().clip(lower=1),
                                 color="pnl", color_continuous_scale="RdYlGn",
                                 labels={"volume": "Volume ($)", "pnl": "PnL ($)"})
        st.plotly_chart(fig_scatter, use_container_width=True)

        # Table
        st.dataframe(df_lb[["rank", "username", "pnl", "volume", "verified", "proxy_wallet"]],
                      use_container_width=True, hide_index=True)


# ===== TAB 2: Trader Analysis =====
with tab_traders:
    st.subheader("Trader Classification Explorer")

    # Build trader metrics from trades
    df_trader_stats = load_df("""
        SELECT
            t.proxy_wallet,
            w.username,
            COUNT(*) as trade_count,
            COUNT(DISTINCT t.condition_id) as markets_traded,
            SUM(CASE WHEN t.side = 'BUY' THEN 1 ELSE 0 END) as buys,
            SUM(CASE WHEN t.side = 'SELL' THEN 1 ELSE 0 END) as sells,
            AVG(t.size) as avg_size,
            SUM(t.size * t.price) as total_volume,
            MIN(t.timestamp) as first_trade,
            MAX(t.timestamp) as last_trade
        FROM trades t
        JOIN wallets w ON t.proxy_wallet = w.proxy_wallet
        GROUP BY t.proxy_wallet
        HAVING trade_count >= 2
        ORDER BY total_volume DESC
    """)

    if df_trader_stats.empty:
        st.info("No trade data yet. Run the collector.")
    else:
        # Classification by volume tiers
        df_ts = df_trader_stats.copy()
        q75 = df_ts["total_volume"].quantile(0.75)
        q90 = df_ts["total_volume"].quantile(0.90)
        q99 = df_ts["total_volume"].quantile(0.99)

        def classify_tier(vol):
            if vol >= q99:
                return "Whale"
            elif vol >= q90:
                return "Heavy"
            elif vol >= q75:
                return "Active"
            else:
                return "Retail"

        df_ts["tier"] = df_ts["total_volume"].apply(classify_tier)
        df_ts["buy_ratio"] = df_ts["buys"] / df_ts["trade_count"]

        col1, col2, col3, col4 = st.columns(4)
        tier_counts = df_ts["tier"].value_counts()
        for col, tier in zip([col1, col2, col3, col4], ["Whale", "Heavy", "Active", "Retail"]):
            with col:
                st.metric(tier, tier_counts.get(tier, 0))

        # Volume by tier
        fig_tier = px.box(df_ts, x="tier", y="total_volume", title="Volume Distribution by Tier",
                          category_orders={"tier": ["Whale", "Heavy", "Active", "Retail"]},
                          color="tier", log_y=True,
                          labels={"total_volume": "Total Volume ($)", "tier": "Tier"})
        st.plotly_chart(fig_tier, use_container_width=True)

        # Trade count vs Markets traded
        fig_activity = px.scatter(df_ts, x="trade_count", y="markets_traded",
                                  color="tier", hover_data=["username", "total_volume"],
                                  title="Activity Pattern: Trades vs Markets Diversification",
                                  category_orders={"tier": ["Whale", "Heavy", "Active", "Retail"]},
                                  labels={"trade_count": "Total Trades", "markets_traded": "Distinct Markets"})
        st.plotly_chart(fig_activity, use_container_width=True)

        # Buy ratio distribution
        fig_buy = px.histogram(df_ts, x="buy_ratio", color="tier", nbins=20,
                               title="Buy Ratio Distribution (1.0 = only buys, 0.0 = only sells)",
                               category_orders={"tier": ["Whale", "Heavy", "Active", "Retail"]},
                               labels={"buy_ratio": "Buy Ratio"})
        st.plotly_chart(fig_buy, use_container_width=True)

        st.dataframe(df_ts[["username", "tier", "trade_count", "markets_traded",
                            "total_volume", "avg_size", "buy_ratio", "proxy_wallet"]]
                     .head(100), use_container_width=True, hide_index=True)


# ===== TAB 3: Market Intel =====
with tab_markets:
    st.subheader("Market Intelligence")

    df_markets = load_df("SELECT * FROM markets ORDER BY volume DESC")

    if df_markets.empty:
        st.info("No market data yet. Run the collector.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Markets", len(df_markets))
        with col2:
            st.metric("Active", df_markets["active"].sum())

        # Volume distribution
        fig_vol = px.bar(df_markets.head(30), x="title", y="volume",
                         title="Top 30 Markets by Volume",
                         labels={"volume": "Volume ($)", "title": "Market"})
        fig_vol.update_xaxes(tickangle=45)
        st.plotly_chart(fig_vol, use_container_width=True)

        # Trades per market
        df_market_trades = load_df("""
            SELECT condition_id, COUNT(*) as trade_count,
                   COUNT(DISTINCT proxy_wallet) as unique_traders,
                   title
            FROM trades
            GROUP BY condition_id
            ORDER BY trade_count DESC
            LIMIT 30
        """)
        if not df_market_trades.empty:
            fig_mt = px.scatter(df_market_trades, x="unique_traders", y="trade_count",
                                hover_data=["title"], size="trade_count",
                                title="Market Activity: Unique Traders vs Trade Count",
                                labels={"unique_traders": "Unique Traders", "trade_count": "Trades"})
            st.plotly_chart(fig_mt, use_container_width=True)

        st.dataframe(df_markets[["title", "volume", "liquidity", "active", "end_date", "condition_id"]]
                     .head(50), use_container_width=True, hide_index=True)


# ===== TAB 4: Hypothesis Lab =====
with tab_hypo:
    st.subheader("Hypothesis Testing Lab")
    st.markdown("Explore hypotheses about trader reliability and signal quality.")

    hypo = st.selectbox("Select Hypothesis", [
        "H1: High-PnL traders have more diversified portfolios",
        "H2: Verified traders outperform non-verified",
        "H3: Early movers in markets have better returns",
        "H4: Whale movements predict market direction",
        "H5: Consistent traders (many markets) vs concentrated bettors",
    ])

    if hypo.startswith("H1"):
        st.markdown("**H1:** Do high-PnL traders spread bets across more markets?")
        df_h1 = load_df("""
            SELECT ls.pnl, COUNT(DISTINCT t.condition_id) as markets_traded,
                   COUNT(t.id) as trade_count, w.username
            FROM leaderboard_snapshots ls
            JOIN wallets w ON ls.proxy_wallet = w.proxy_wallet
            LEFT JOIN trades t ON ls.proxy_wallet = t.proxy_wallet
            WHERE ls.time_period = 'ALL' AND ls.category = 'OVERALL'
            GROUP BY ls.proxy_wallet
            HAVING trade_count > 0
        """)
        if not df_h1.empty:
            fig = px.scatter(df_h1, x="pnl", y="markets_traded", hover_data=["username"],
                             trendline="ols", title="PnL vs Portfolio Diversification",
                             labels={"pnl": "PnL ($)", "markets_traded": "Markets Traded"})
            st.plotly_chart(fig, use_container_width=True)

            corr = df_h1[["pnl", "markets_traded"]].corr().iloc[0, 1]
            st.metric("Correlation (PnL ↔ Markets Traded)", f"{corr:.3f}")
        else:
            st.info("Need leaderboard + trades data to test this hypothesis.")

    elif hypo.startswith("H2"):
        st.markdown("**H2:** Do verified users have better PnL than non-verified?")
        df_h2 = load_df("""
            SELECT w.verified, ls.pnl, ls.volume, w.username
            FROM leaderboard_snapshots ls
            JOIN wallets w ON ls.proxy_wallet = w.proxy_wallet
            WHERE ls.time_period = 'ALL' AND ls.category = 'OVERALL'
        """)
        if not df_h2.empty:
            df_h2["verified_label"] = df_h2["verified"].map({1: "Verified", 0: "Not Verified"})
            fig = px.box(df_h2, x="verified_label", y="pnl", color="verified_label",
                         title="PnL by Verification Status",
                         labels={"pnl": "PnL ($)", "verified_label": ""})
            st.plotly_chart(fig, use_container_width=True)

            summary = df_h2.groupby("verified_label")["pnl"].agg(["mean", "median", "count"])
            st.dataframe(summary, use_container_width=True)
        else:
            st.info("Need leaderboard data to test this hypothesis.")

    elif hypo.startswith("H3"):
        st.markdown("**H3:** Do traders who enter markets early get better prices?")
        df_h3 = load_df("""
            SELECT t.proxy_wallet, t.condition_id, t.price, t.side, t.timestamp,
                   t.title,
                   ROW_NUMBER() OVER (PARTITION BY t.condition_id ORDER BY t.timestamp ASC) as trade_order
            FROM trades t
            WHERE t.side = 'BUY'
            ORDER BY t.condition_id, t.timestamp
        """)
        if not df_h3.empty:
            df_h3["is_early"] = df_h3["trade_order"] <= 5
            early_avg = df_h3[df_h3["is_early"]]["price"].mean()
            late_avg = df_h3[~df_h3["is_early"]]["price"].mean()
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Avg Price (Early Movers, top 5)", f"${early_avg:.3f}")
            with col2:
                st.metric("Avg Price (Later Movers)", f"${late_avg:.3f}")
            with col3:
                diff = late_avg - early_avg
                st.metric("Price Disadvantage", f"${diff:.3f}", delta=f"{diff/early_avg*100:.1f}%")

            fig = px.histogram(df_h3, x="price", color=df_h3["is_early"].map({True: "Early (top 5)", False: "Later"}),
                               nbins=30, barmode="overlay", title="Entry Price: Early vs Late Movers",
                               labels={"price": "Entry Price", "color": "Timing"})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Need trades data to test this hypothesis.")

    elif hypo.startswith("H4"):
        st.markdown("**H4:** When whales buy, does the market follow?")
        st.markdown("_Requires position snapshots over time to validate. Current data shows a single snapshot._")

        df_h4 = load_df("""
            SELECT t.condition_id, t.title, t.side, t.size, t.price, t.timestamp,
                   t.proxy_wallet
            FROM trades t
            WHERE t.proxy_wallet IN (
                SELECT proxy_wallet FROM leaderboard_snapshots
                WHERE time_period = 'ALL' AND category = 'OVERALL'
                ORDER BY pnl DESC LIMIT 10
            )
            ORDER BY t.timestamp DESC
            LIMIT 200
        """)
        if not df_h4.empty:
            st.markdown("**Recent trades by top-10 PnL traders:**")
            st.dataframe(df_h4[["title", "side", "size", "price", "timestamp", "proxy_wallet"]]
                        .head(50), use_container_width=True, hide_index=True)

            side_counts = df_h4.groupby(["title", "side"]).size().reset_index(name="count")
            fig = px.bar(side_counts.head(30), x="title", y="count", color="side",
                         barmode="group", title="Top-10 PnL Traders: Buy vs Sell by Market")
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Need leaderboard + trades data.")

    elif hypo.startswith("H5"):
        st.markdown("**H5:** Do consistent traders (many markets) outperform concentrated bettors?")
        df_h5 = load_df("""
            SELECT t.proxy_wallet, w.username,
                   COUNT(DISTINCT t.condition_id) as markets_count,
                   COUNT(*) as trade_count,
                   ls.pnl
            FROM trades t
            JOIN wallets w ON t.proxy_wallet = w.proxy_wallet
            LEFT JOIN leaderboard_snapshots ls ON t.proxy_wallet = ls.proxy_wallet
                AND ls.time_period = 'ALL' AND ls.category = 'OVERALL'
            GROUP BY t.proxy_wallet
            HAVING trade_count >= 5
        """)
        if not df_h5.empty and df_h5["pnl"].notna().any():
            median_markets = df_h5["markets_count"].median()
            df_h5["style"] = df_h5["markets_count"].apply(
                lambda x: "Diversified" if x >= median_markets else "Concentrated"
            )
            fig = px.box(df_h5, x="style", y="pnl", color="style",
                         title="PnL: Diversified vs Concentrated Traders",
                         labels={"pnl": "PnL ($)", "style": "Trading Style"})
            st.plotly_chart(fig, use_container_width=True)

            summary = df_h5.groupby("style")["pnl"].agg(["mean", "median", "count"])
            st.dataframe(summary, use_container_width=True)
        else:
            st.info("Need trades + leaderboard data with PnL.")


# ===== TAB 5: Deep Dive =====
with tab_deep:
    st.subheader("Wallet Deep Dive")

    # Wallet selector
    df_wallets = load_df("SELECT proxy_wallet, username FROM wallets ORDER BY username")
    if df_wallets.empty:
        st.info("No wallets in database.")
    else:
        options = [f"{r['username'] or 'anon'} ({r['proxy_wallet'][:10]}...)" for _, r in df_wallets.iterrows()]
        wallet_map = dict(zip(options, df_wallets["proxy_wallet"]))

        selected = st.selectbox("Select Wallet", options)
        wallet = wallet_map[selected]

        st.code(wallet, language=None)

        # Trades
        df_wt = load_df("SELECT * FROM trades WHERE proxy_wallet = ? ORDER BY timestamp DESC", (wallet,))
        # Positions
        df_wp = load_df("SELECT * FROM positions WHERE proxy_wallet = ? ORDER BY current_value DESC", (wallet,))
        # Leaderboard
        df_wl = load_df("SELECT * FROM leaderboard_snapshots WHERE proxy_wallet = ?", (wallet,))

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Trades", len(df_wt))
        with col2:
            st.metric("Open Positions", len(df_wp))
        with col3:
            if not df_wl.empty:
                best_pnl = df_wl["pnl"].max()
                st.metric("Best PnL (leaderboard)", f"${best_pnl:,.0f}" if best_pnl else "N/A")
            else:
                st.metric("Leaderboard", "Not ranked")

        if not df_wt.empty:
            st.markdown("#### Trade History")
            # Timeline
            df_wt_plot = df_wt.copy()
            df_wt_plot["timestamp"] = pd.to_datetime(df_wt_plot["timestamp"], errors="coerce")
            df_wt_plot = df_wt_plot.dropna(subset=["timestamp"])

            if not df_wt_plot.empty:
                fig_timeline = px.scatter(df_wt_plot, x="timestamp", y="price", color="side",
                                          size="size", hover_data=["title", "outcome"],
                                          title="Trade Timeline",
                                          labels={"timestamp": "Time", "price": "Price", "side": "Side"})
                st.plotly_chart(fig_timeline, use_container_width=True)

            # Markets breakdown
            market_breakdown = df_wt.groupby("title").agg(
                trades=("title", "count"),
                avg_price=("price", "mean"),
                total_size=("size", "sum"),
            ).sort_values("trades", ascending=False).head(15)
            st.dataframe(market_breakdown, use_container_width=True)

        if not df_wp.empty:
            st.markdown("#### Current Positions")
            fig_pos = px.bar(df_wp.head(20), x="title", y="current_value", color="cash_pnl",
                             color_continuous_scale="RdYlGn",
                             title="Current Positions (top 20 by value)",
                             labels={"current_value": "Current Value ($)", "title": "Market"})
            fig_pos.update_xaxes(tickangle=45)
            st.plotly_chart(fig_pos, use_container_width=True)

            st.dataframe(df_wp[["title", "outcome", "size", "avg_price", "current_value",
                                "cash_pnl", "percent_pnl", "realized_pnl"]]
                        .head(30), use_container_width=True, hide_index=True)
