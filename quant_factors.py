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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
os.makedirs("charts", exist_ok=True)


df_mom = pd.read_sql("""
    WITH r AS (SELECT ticker, close,
        LAG(close,63) OVER (PARTITION BY ticker ORDER BY date) AS c63,
        ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn FROM prices)
    SELECT ticker, ROUND((close/c63-1)*100,1) AS mom FROM r
    WHERE rn=1 AND c63 IS NOT NULL ORDER BY mom DESC;
""", conn)
plt.figure(figsize=(9,5))
colors = ["#55a868" if v>=0 else "#c44e52" for v in df_mom["mom"]]
plt.bar(df_mom["ticker"], df_mom["mom"], color=colors)
plt.title("63-Day Momentum by Stock"); plt.ylabel("Momentum (%)")
plt.axhline(0, color="black", lw=0.8); plt.xticks(rotation=45, ha="right")
plt.tight_layout(); plt.savefig("charts/momentum.png", dpi=150); plt.close()


df_rr = pd.read_sql("""
    WITH rets AS (SELECT ticker,
        close/LAG(close) OVER (PARTITION BY ticker ORDER BY date)-1 AS r FROM prices)
    SELECT ticker, AVG(r)*252*100 AS ret, STDDEV(r)*15.874*100 AS vol
    FROM rets WHERE r IS NOT NULL GROUP BY ticker;
""", conn)
plt.figure(figsize=(8,6))
plt.scatter(df_rr["vol"], df_rr["ret"], color="#4c72b0")
for _, row in df_rr.iterrows():
    plt.annotate(row["ticker"], (row["vol"], row["ret"]), fontsize=8,
                 xytext=(4,4), textcoords="offset points")
plt.title("Risk vs Return"); plt.xlabel("Annualised Volatility (%)"); plt.ylabel("Annualised Return (%)")
plt.axhline(0, color="gray", lw=0.6); plt.grid(alpha=0.3)
plt.tight_layout(); plt.savefig("charts/risk_return.png", dpi=150); plt.close()

print("Saved charts to charts/")

conn.close()
print("\nDone.")
