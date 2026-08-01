# quant_factors.py
# A quant factor database built with SQL (SQLite): loads real market
# data and computes momentum, returns, volatility and rankings using
# window functions, CTEs and a custom STDDEV aggregate.

import sqlite3
import statistics
import yfinance as yf
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 120)

TICKERS = ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM",
           "V","WMT","KO","XOM","JNJ","PG","HD"]

# ==================================================================
# 1. Download prices and load into SQLite (long format)
# ==================================================================
print("Downloading prices...")
px = yf.download(TICKERS, start="2022-01-01", end="2024-01-01", auto_adjust=True)["Close"]
long = (px.reset_index()
          .melt(id_vars="Date", var_name="ticker", value_name="close")
          .dropna())
long["Date"] = long["Date"].astype(str)

conn = sqlite3.connect(":memory:")
long.rename(columns={"Date":"date"}).to_sql("prices", conn, index=False)
conn.execute("CREATE INDEX idx_tk ON prices(ticker, date);")

# custom STDDEV aggregate (SQLite has no built-in stddev)
class StdDev:
    def __init__(self): self.vals = []
    def step(self, v):
        if v is not None: self.vals.append(v)
    def finalize(self):
        return statistics.stdev(self.vals) if len(self.vals) > 1 else 0.0
conn.create_aggregate("STDDEV", 1, StdDev)

print(f"Loaded {len(long)} rows across {long['ticker'].nunique()} tickers.\n")

def run(title, sql):
    print("\n" + "="*70); print(title); print("="*70)
    print(pd.read_sql(sql, conn).to_string(index=False))

# ==================================================================
# 2. SQL analytics
# ==================================================================

run("Daily returns (LAG window function) — sample", """
    SELECT ticker, date, ROUND(close,2) AS close,
           ROUND((close / LAG(close) OVER (PARTITION BY ticker ORDER BY date) - 1)*100, 3) AS daily_ret_pct
    FROM prices
    WHERE ticker = 'AAPL'
    ORDER BY date DESC
    LIMIT 5;
""")

run("63-day Momentum ranking (LAG + RANK)", """
    WITH r AS (
        SELECT ticker, date, close,
               LAG(close, 63) OVER (PARTITION BY ticker ORDER BY date) AS close_63,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
        FROM prices
    )
    SELECT ticker,
           ROUND((close/close_63 - 1)*100, 1) AS momentum_63d_pct,
           RANK() OVER (ORDER BY close/close_63 DESC) AS rank
    FROM r
    WHERE rn = 1 AND close_63 IS NOT NULL
    ORDER BY momentum_63d_pct DESC;
""")

run("Risk / Return by stock (custom STDDEV, GROUP BY)", """
    WITH rets AS (
        SELECT ticker,
               close / LAG(close) OVER (PARTITION BY ticker ORDER BY date) - 1 AS r
        FROM prices
    )
    SELECT ticker,
           ROUND(AVG(r)*252*100, 1)             AS ann_return_pct,
           ROUND(STDDEV(r)*15.874*100, 1)       AS ann_vol_pct,
           ROUND(AVG(r)*252 / (STDDEV(r)*15.874), 2) AS sharpe
    FROM rets
    WHERE r IS NOT NULL
    GROUP BY ticker
    ORDER BY sharpe DESC;
""")

run("Total return over full period (first vs last close)", """
    WITH ordered AS (
        SELECT ticker, date, close,
               FIRST_VALUE(close) OVER (PARTITION BY ticker ORDER BY date) AS first_close,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
        FROM prices
    )
    SELECT ticker,
           ROUND((close/first_close - 1)*100, 1) AS total_return_pct
    FROM ordered
    WHERE rn = 1
    ORDER BY total_return_pct DESC;
""")

run("Momentum factor portfolio: top 5 vs bottom 5 (CTE + CASE)", """
    WITH mom AS (
        SELECT ticker, close/close_63 - 1 AS m FROM (
            SELECT ticker, close,
                   LAG(close,63) OVER (PARTITION BY ticker ORDER BY date) AS close_63,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM prices
        ) WHERE rn=1 AND close_63 IS NOT NULL
    ),
    ranked AS (
        SELECT ticker, m,
               RANK() OVER (ORDER BY m DESC) AS hi,
               RANK() OVER (ORDER BY m ASC)  AS lo
        FROM mom
    )
    SELECT CASE WHEN hi<=5 THEN 'Top 5 (long)' WHEN lo<=5 THEN 'Bottom 5 (short)' END AS bucket,
           COUNT(*) AS stocks,
           ROUND(AVG(m)*100, 1) AS avg_momentum_pct
    FROM ranked
    WHERE hi<=5 OR lo<=5
    GROUP BY bucket;
""")

conn.close()
print("\nDone.")
