# ALPHA HYPOTHESIS ENGINE — PRD v2.0

## Knowledge Graph-Centric Investment Intelligence

**Version 2.0 | Febrero 2026 | Southlab.ai**

---

## 1. Executive Summary

Alpha Hypothesis Engine (AHE) is a **knowledge graph-centric investment intelligence system** that combines Claude Opus 4.6, real-time financial data from 15+ sources, and a continuously evolving financial knowledge graph to deliver institutional-grade investment analysis for individual investors.

> **CORE DESIGN PRINCIPLE:** The Knowledge Graph IS the product. Every piece of data, every hypothesis, every relationship between companies, sectors, macro variables, and market events lives as structured nodes and edges in a temporal financial knowledge graph. The LLM is the reasoning engine that reads, writes, and traverses this graph. The human sees it as an interactive mindmap. This is not RAG with a graph bolted on — the graph is the central nervous system.

The system implements **Hypothesis-Driven Investing** where the LLM **never acts as a predictor**. Instead, it structures hypotheses as graph substructures, validates them against fresh data via deterministic Python, and presents recommendations with full causal traceability. Every calculation that touches money is executed in Python with hardcoded risk limits. Every decision requires explicit human approval.

---

## 2. The Paradigm Shift: From Flat Data to Living Knowledge

### 2.1 Why Every Existing Tool Fails

| Category | Examples | Fatal Flaw |
|----------|----------|------------|
| Chat + Search | ChatGPT, Perplexity Finance | No memory. No relationships. Each query starts from zero. Cannot reason across entities. |
| Dashboard + AI | Bloomberg + GPT, Koyfin | Data is siloed in tables. AI is a chatbot overlay. No graph connecting companies → supply chains → macro → portfolio. |
| RAG-based | Custom vector DB solutions | Chunks text into fragments. Loses entity relationships. Cannot do multi-hop reasoning. |

### 2.2 The Knowledge Graph Advantage

**Multi-hop Causal Reasoning:** Query: "What happens to my portfolio if China restricts rare earth exports?" Graph traverses: Portfolio → holdings → NVDA → depends_on → TSMC → uses_material → gallium → sourced_from → China → restriction_probability → Polymarket 23%.

**Hidden Concentration Detection:** Your 10-stock portfolio looks diversified. But the graph reveals that 6 of 10 holdings depend on the same macro variable (hyperscaler capex). A table can't show this. A graph makes it obvious.

**Hypothesis as Subgraph:** Each hypothesis becomes a connected subgraph: thesis → assumptions → kill signals → data metrics → portfolio positions. When new data arrives, the system traverses the graph to find all affected hypotheses automatically.

---

## 3. System Architecture

```
[Data Sources] → [Ingestion Pipeline] → [Neo4j Knowledge Graph] → [LightRAG + Graph Traversal] → [Claude Opus 4.6 via MCP] → [Deterministic Python Validation] → [Interactive Mindmap UI] → [Human Decision] → [Alpaca Execution via MCP]
```

### The Five Layers

| Layer | Components | Role |
|-------|-----------|------|
| Data Ingestion | OpenBB, FRED, SEC, Finnhub, Polymarket, Kalshi, Unusual Whales, yFinance | Continuous data collection → graph-ready entities |
| Knowledge Graph | Neo4j + LightRAG + Leiden Clustering | Central nervous system. All entities, relationships, hypotheses, portfolio state |
| Intelligence Engine | Claude Opus 4.6 + 6 Agents + MCP Servers | Reads, reasons, writes to graph. Never calculates. |
| Validation Layer | Python (pandas, numpy, scipy, PyPortfolioOpt) + Hardcoded Rules | 100% deterministic. Every number that touches money. |
| Human Interface | React Mindmap + Neo4j Visualization + Dashboard | Interactive mindmap. Click any node. Approve/reject inline. |

---

## 4. The Financial Knowledge Graph

### 4.1 Node Types

| Node Type | Examples | Key Properties |
|-----------|----------|----------------|
| Company | NVDA, TSMC, MSFT | ticker, sector_gics, market_cap, fundamentals_snapshot |
| Sector | Semiconductors, Cloud | gics_code, correlation_to_spy |
| Person | Jensen Huang, Satya Nadella | role, company, insider_signal |
| MacroVariable | Fed Funds Rate, CPI, VIX | current_value, trend, regime_classification |
| Event | FOMC Meeting, NVDA Earnings | date, probability (Polymarket), impact_magnitude |
| Hypothesis | "AI capex cycle continues" | thesis, confidence_score, status, kill_criteria[] |
| Assumption | "Azure revenue >25% YoY" | metric, threshold, current_value, status |
| KillSignal | "Capex guidance down >10%" | trigger_condition, triggered (bool) |
| PortfolioPosition | Long NVDA 4.2% | weight, entry_price, stop_loss, pnl |
| MarketRegime | Risk-On / Risk-Off / Crisis | classification, indicators{}, confidence |
| PredictionMarket | "Fed cuts before July?" | probability, volume_24h, platform |
| ResearchDocument | NVDA Q4 transcript | source, sentiment, key_topics[] |

### 4.2 Relationship Types

| Relationship | From → To | Properties |
|-------------|-----------|------------|
| SUPPLIES_TO | Company → Company | product, revenue_dependency_pct |
| COMPETES_WITH | Company → Company | market_overlap_pct |
| DEPENDS_ON_MACRO | Company → MacroVariable | sensitivity_beta, mechanism |
| CATALYZED_BY | Hypothesis → Event | expected_impact, probability |
| ASSUMES | Hypothesis → Assumption | criticality |
| KILLED_BY | Hypothesis → KillSignal | severity |
| POSITIONS_IN | Hypothesis → PortfolioPosition | allocation, conviction |
| CORRELATES_WITH | Company → Company | correlation_60d, beta |
| PRICED_BY_MARKET | Event → PredictionMarket | probability, trend |

### 4.3 Temporal Versioning

- **valid_from / valid_to**: Every relationship has a time window. History accumulates, never deletes.
- **snapshot_version**: Fundamentals versioned per earnings cycle for QoQ comparison.
- **confidence_decay**: Relationships lose confidence over time. Stale relationships surface for review.

---

## 5. Graph-Powered Intelligence Pipeline

### 5.1 Generate Hypotheses
- **Trigger**: New data arrives
- **Graph**: LightRAG identifies affected subgraphs
- **Claude**: Receives graph context → generates structured hypothesis
- **Output**: New Hypothesis subgraph with Assumptions, KillSignals, Company links

### 5.2 Validate with Data
- **100% Python**: Backtesting, IC, Sharpe, factor exposure, correlation
- **Output**: validation_score (0-100) written to Hypothesis node

### 5.3 Construct Position
- **100% Python**: Kelly Criterion, ATR stops, correlation-aware allocation
- **Output**: PortfolioPosition node with target weight, stops

### 5.4 Monitor Continuously
- **Graph-native**: Traverse Hypothesis → Assumption edges every 4h
- **Checks**: Assumption thresholds, KillSignal triggers, Polymarket shifts, regime changes
- **Output**: Alerts with full causal chain from graph

### 5.5 Decide with Human
- **Always**: Visual subgraph + confidence + pro/contra + portfolio impact
- **One-click**: Approve/reject with audit trail in graph

---

## 6. Complete Data Stack

| Source | Cost | Graph Role | Rate Limit |
|--------|------|-----------|------------|
| OpenBB Platform | Free | Market data → Company nodes | Per-provider |
| FRED API | Free | 816K+ series → MacroVariable nodes | Unlimited |
| SEC EDGAR | Free | 13F, insider → edges. 10-K → ResearchDocument | 10/sec |
| FMP API | Free | Transcripts → ResearchDocument | 250/day |
| Finnhub | Free | Supply chain → SUPPLIES_TO. Sentiment. | 60/min |
| Polymarket | Free | Probabilities → PredictionMarket nodes | 1K/hour |
| Kalshi | Free | CFTC probabilities → cross-validation | 1K/hour |
| yFinance | Free | OHLCV → Company price data | Informal |
| Fama-French | Free | Factors → Company properties | Unlimited |
| Unusual Whales | $37/mo | Options flow + dark pool → signals | Generous |
| Polygon.io | $29/mo | Tick data → institutional accuracy | Unlimited* |

**Total: $0/mo (functional) to $66/mo (complete). Compare Bloomberg: $24,000/yr.**

---

## 7. MCP Server Constellation

| MCP Server | Source | Capabilities |
|-----------|--------|-------------|
| neo4j-mcp | Official | Cypher read/write on FKG. Schema. Graph algorithms. |
| openbb-mcp-server | Official | 100+ financial endpoints as tools |
| alpaca-mcp-server | Official | Paper + live trading. Portfolio. Options. |
| polymarket-mcp | Community | Prediction market queries |
| ahe-validation | Custom | Python validation tools: Kelly, VaR, correlation |
| ahe-graph-builder | Custom | Entity extraction → graph construction |

---

## 8. Graph Construction Engine

### 8.1 LightRAG (EMNLP 2025)
- **Dual-Level Retrieval**: Low-level (entity-specific) + High-level (multi-hop neighborhoods)
- **Incremental Updates**: Process only delta. No full reprocessing.
- **10x fewer tokens** than Microsoft GraphRAG

### 8.2 Entity Extraction Pipeline
1. Document ingestion → semantic chunking
2. Claude extracts entities (Companies, People, Metrics, Events)
3. Relationship extraction with ontology-guided typing
4. Deduplication & entity resolution
5. Leiden clustering → community detection → summary nodes

### 8.3 Automated Maintenance
- **Daily**: Prices, macro, Polymarket probabilities
- **Weekly**: Insider trading, short interest, supply chain validation
- **On Earnings**: Full extraction, Hypothesis re-evaluation, QoQ comparison
- **Confidence Decay**: Weekly job reduces stale relationship confidence

---

## 9. Agent Architecture

| Agent | Graph Access | MCP Servers | Output |
|-------|-------------|-------------|--------|
| Hypothesis Generator | R: full, W: Hypothesis/Assumption/KillSignal | neo4j, openbb, polymarket | Hypothesis subgraph |
| Data Validator | R: Hypothesis, W: scores | ahe-validation, openbb | Confidence 0-100 |
| Risk Sentinel | R: portfolio, W: risk metrics | ahe-validation, neo4j | VaR, drawdown, correlations |
| Position Architect | R: Hypothesis+Risk, W: Position | ahe-validation, alpaca | Weight, stops, targets |
| Signal Monitor | R: all active, W: alerts | neo4j, openbb, polymarket | Alerts with causal context |
| Decision Presenter | R: complete, W: none | neo4j | Recommendation + graph viz |

---

## 10. Human Interface: Interactive Mindmap

### Mindmap Mode (Exploration)
- **Center**: Portfolio node
- **First Ring**: Holdings (color = P&L, size = weight)
- **Second Ring**: Hypotheses (bright = active, dim = inactive)
- **Third Ring**: Assumptions/KillSignals (green/yellow/red)
- **Macro Layer**: Background. Edges light up on changes.
- **Event Layer**: Catalysts with Polymarket probability badges.

### Interaction
- **Click node**: Side panel with details + Claude summary
- **Click edge**: Relationship details, evidence, confidence, history
- **Ask question**: NL → Cypher via neo4j-mcp → graph highlight
- **Approve/Reject**: One-click with audit trail

### Dashboard Mode
- Morning Briefing (filtered to YOUR holdings)
- Portfolio Health (green/yellow/red per position)
- Hypothesis Scoreboard (ranked by confidence + P&L)
- Risk Map (correlation heatmap, factor radar)
- Brier Score Tracker (calibration over time)

---

## 11. Risk Management: Hardcoded & Immutable

| Rule | Threshold | Enforcement |
|------|-----------|-------------|
| Max Single Position | 5% | Python: `if weight > 0.05: reject()` |
| Sector Concentration | 25% per GICS | Neo4j aggregation query |
| Stop Loss | 2x ATR(14) | Checked every 15 min |
| Portfolio Drawdown | -10% from HWM | 50% reduction signal |
| Confidence Threshold | Score > 65 | No position below 65 |
| Min Diversification | 10+ positions | Graph count query |
| Paper Trading First | 90 days | Calendar gate |
| Correlation Guard | Max 0.7 pairwise | Rolling 60d correlation |
| Hypothesis Expiry | 180 days | Auto-review status |

---

## 12. Prompt Engineering

| Technique | Application |
|-----------|-------------|
| Chain-of-Thought + XML | `<thinking>` → `<conclusion>`. XML tags for structured output. |
| Role/Persona | "Senior analyst, 15yr, CFA, [sector from graph]" |
| Causal Forcing | "5 mutually exclusive causal mechanisms" |
| Red Team | "You are a short-seller. 3 scenarios losing >20%" |
| Transcript Analysis | "QoQ comparison: omissions, evasions, tone shifts" |
| Graph-Contextualized | "Given this subgraph: [Cypher result]. Weakest link?" |
| Calibrated Confidence | "Your Brier Score is [X]. Calibrate accordingly." |
| Pre-Mortem | "6 months later, this failed. Write the post-mortem." |

---

## 13. Technical Stack

| Component | Technology |
|-----------|-----------|
| LLM | Claude Opus 4.6 (Max plan, unlimited) |
| Knowledge Graph | Neo4j Community (Docker) |
| Graph Indexing | LightRAG (EMNLP 2025) |
| Development | Claude Code (Max, Opus 4.6) |
| Data Platform | OpenBB Platform v4.6 |
| Validation | Python 3.11+ (pandas, numpy, scipy, PyPortfolioOpt) |
| Trading | Alpaca MCP Server (paper → live) |
| Predictions | Polymarket + Kalshi APIs |
| Frontend | React + Neo4j Viz + Recharts |
| Storage | Neo4j (graph) + SQLite (journal) + JSON (config) |

**Monthly Cost: $100–166/mo** (Claude Max + optional data). Compare Bloomberg $2,000/mo.

---

## 14. Gap Analysis (With Knowledge Graph)

| Gap | Without Graph | With Graph |
|-----|-------------|------------|
| Multi-hop reasoning | 60% | 90% |
| Primary information | 40% | 85% |
| Reading between lines | 50% | 80% |
| Skin in the game | 0% | 90% |
| Sizing & timing | 70% | 95% |
| 2nd/3rd order thinking | 40% | 85% |
| Overconfidence | 30% | 80% |
| Memorization | 50% | 90% |
| Regime adaptation | 45% | 85% |
| Modeling players | 30% | 70% |

**Average: 46% → 85%**

---

## 15. Academic Foundation

- **FinKario (2025)**: KG-RAG outperforms LLMs + institutional strategies
- **RAG-FLARKO (2025)**: Multi-stage KG retrieval maximizes gains for constrained models
- **LightRAG (EMNLP 2025)**: 10x fewer tokens than GraphRAG, incremental updates
- **Microsoft GraphRAG (2024)**: Pioneered LLM-generated KGs + Leiden clustering
- **FinReflectKG (2025)**: Agentic KG construction from SEC filings
- **FINSABER (KDD 2026)**: LLMs = great tools, unreliable predictors
- **TradingAgents (AAAI 2025)**: Multi-agent > single-agent in trading
- **Alpha-GPT 2.0 (EMNLP 2025)**: Human-AI hypothesis framework

---

## 16. Why This Wins

1. **KNOWLEDGE COMPOUNDS**: Every analysis enriches the graph. The 1000th is dramatically better than the 1st.
2. **INVISIBLE COMPLEXITY**: Human sees mindmap. Behind it: 6 agents, 15 sources, thousands of graph nodes.
3. **RELATIONAL REASONING**: Only retail tool that traces multi-hop paths to your portfolio.
4. **INSTITUTIONAL DISCIPLINE + INDIVIDUAL AGILITY**: Fund-grade risk rules + research depth. Act in minutes.
5. **COST ASYMMETRY**: $100-166/mo for capabilities costing institutions $50,000+/mo.

---

*Alpha Hypothesis Engine — Southlab.ai — Confidential*
