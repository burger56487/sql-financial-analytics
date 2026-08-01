# SQL Financial Analytics

Two SQL (SQLite) analytics projects demonstrating schema design, JOINs,
aggregations, window functions, CTEs and custom aggregates — applied to
private-markets and quantitative use cases.

## 1. PE/VC Deal Database (`pe_vc_deals.py`)
A private-equity / venture-capital portfolio database with analytical queries:
- Portfolio overview, MOIC, realised vs unrealised
- Performance by sector, stage and vintage year
- Top deals (window `RANK`), win/loss distribution
- Return concentration (CTE) — the top 3 deals drive ~65% of value, reproducing
  the venture power-law

**SQL used:** `CREATE TABLE` (keys), `JOIN`, `GROUP BY`, `CASE`,
window functions (`RANK`, `SUM OVER`), CTEs, date functions.

## 2. Quant Factor Database (`quant_factors.py`)
Loads real market data (via yfinance) into SQLite and computes factors in SQL:
- Daily returns (`LAG`), 63-day momentum ranking (`LAG` + `RANK`)
- Risk/return per stock: annualised return, volatility, Sharpe
  (via a **custom `STDDEV` aggregate**)
- Total return, and a momentum long/short factor portfolio (top 5 vs bottom 5)

**SQL used:** window functions (`LAG`, `RANK`, `ROW_NUMBER`, `FIRST_VALUE`),
multi-level CTEs, custom aggregate function, indexing.

## How to Run
```bash
pip install matplotlib
pip install yfinance pandas
python pe_vc_deals.py
python quant_factors.py
