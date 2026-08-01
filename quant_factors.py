# quant_factors.py
# SQL-based cross-sectional momentum factor test.
# At each month-end: rank stocks by 12-1 momentum (SQL window functions),
# form quintile long/short portfolios, then measure NEXT-month returns.
# Reports long-short performance, Information Coefficient (IC), turnover
# and cost-adjusted results.

import os
import numpy as np
import pandas as pd
import yfinance as yf

pd.set_option("display.width", 120)
import sqlite3

TICKERS = [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM","V","WMT",
    "PG","MA","HD","BAC","XOM","CVX","KO","PEP","ABBV","MRK",
    "COST","MCD","CSCO","ADBE","CRM","NKE","INTC","T","VZ","DIS",
]
START, END = "2015-01-01", "2024-01-01"   # longer history for monthly test
RF_ANNUAL = 0.04
COST_BPS = 20                              # per-leg turnover cost

# ==================================================================
# 1. Data (cached for reproducibility)
# ==================================================================
def get_prices():
    os.makedirs("data", exist_ok=True)
    cache = f"data/px_{START}_{END}.csv"
    if os.path.exists(cache):
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    px = yf.download(TICKERS, start=START, end=END, auto_adjust=True)["Close"]
    px = px.dropna(axis=1, how="all")
    px.to_csv(cache)
    return px

print("Loading prices...")
px = get_prices()
long = (px.reset_index().melt(id_vars="Date", var_name="ticker", value_name="close")
          .dropna())
long["date"] = pd.to_datetime(long["Date"]).astype(str)
long = long[["date","ticker","close"]]
print(f"Loaded {long['ticker'].nunique()} tickers, {long['date'].nunique()} days.\n")

conn = sqlite3.connect(":memory:")
long.to_sql("prices", conn, index=False)
conn.execute("CREATE INDEX idx ON prices(ticker, date);")

# ==================================================================
# 2. SQL: build monthly factor panel (momentum + forward return + quintile)
#    - momentum = 12-1 month (skip most recent month, classic)
#    - forward return = NEXT month return (no look-ahead)
# ==================================================================
panel_sql = """
WITH me AS (   -- month-end row per ticker
    SELECT ticker, date, close,
           strftime('%Y-%m', date) AS ym,
           ROW_NUMBER() OVER (PARTITION BY ticker, strftime('%Y-%m', date)
                              ORDER BY date DESC) AS rn
    FROM prices
),
monthly AS (
    SELECT ticker, ym, close FROM me WHERE rn = 1
),
f AS (
    SELECT ticker, ym, close,
           LAG(close, 1)  OVER (PARTITION BY ticker ORDER BY ym) AS p_1,
           LAG(close, 12) OVER (PARTITION BY ticker ORDER BY ym) AS p_12,
           LEAD(close, 1) OVER (PARTITION BY ticker ORDER BY ym) AS p_fwd
    FROM monthly
),
panel AS (
    SELECT ticker, ym,
           p_1*1.0/p_12 - 1  AS momentum,     -- known at month-end (t-1..t-12)
           p_fwd*1.0/close - 1 AS fwd_ret     -- realised next month
    FROM f
    WHERE p_1 IS NOT NULL AND p_12 IS NOT NULL AND p_fwd IS NOT NULL
)
SELECT ym, ticker, momentum, fwd_ret,
       NTILE(5) OVER (PARTITION BY ym ORDER BY momentum) AS quintile
FROM panel
ORDER BY ym, momentum DESC;
"""
panel = pd.read_sql(panel_sql, conn)

# ==================================================================
# 3. SQL: monthly long-short (Q5 long, Q1 short) forward returns
# ==================================================================
ls_sql = """
WITH me AS (
    SELECT ticker, date, close, strftime('%Y-%m', date) AS ym,
           ROW_NUMBER() OVER (PARTITION BY ticker, strftime('%Y-%m', date) ORDER BY date DESC) AS rn
    FROM prices),
monthly AS (SELECT ticker, ym, close FROM me WHERE rn=1),
f AS (SELECT ticker, ym, close,
        LAG(close,1) OVER (PARTITION BY ticker ORDER BY ym) AS p_1,
        LAG(close,12) OVER (PARTITION BY ticker ORDER BY ym) AS p_12,
        LEAD(close,1) OVER (PARTITION BY ticker ORDER BY ym) AS p_fwd FROM monthly),
panel AS (SELECT ticker, ym, p_1*1.0/p_12-1 AS mom, p_fwd*1.0/close-1 AS fwd
          FROM f WHERE p_1 IS NOT NULL AND p_12 IS NOT NULL AND p_fwd IS NOT NULL),
ranked AS (SELECT ym, fwd, NTILE(5) OVER (PARTITION BY ym ORDER BY mom) AS q FROM panel)
SELECT ym,
       AVG(CASE WHEN q=5 THEN fwd END) AS long_ret,
       AVG(CASE WHEN q=1 THEN fwd END) AS short_ret,
       AVG(CASE WHEN q=5 THEN fwd END) - AVG(CASE WHEN q=1 THEN fwd END) AS ls_ret
FROM ranked GROUP BY ym ORDER BY ym;
"""
ls = pd.read_sql(ls_sql, conn).dropna()
conn.close()

# ==================================================================
# 4. IC (rank correlation of momentum vs forward return, per month)
# ==================================================================
ic = (panel.groupby("ym")
            .apply(lambda g: g["momentum"].corr(g["fwd_ret"], method="spearman"))
            .dropna())

# ==================================================================
# 5. Turnover (long-leg name changes) + cost adjustment
# ==================================================================
longs = {ym: set(g.loc[g["quintile"]==5, "ticker"]) for ym, g in panel.groupby("ym")}
shorts = {ym: set(g.loc[g["quintile"]==1, "ticker"]) for ym, g in panel.groupby("ym")}
months = sorted(longs)
turn = []
for i in range(1, len(months)):
    a, b = months[i-1], months[i]
    lt = len(longs[b] - longs[a]) / max(len(longs[b]), 1)
    stn = len(shorts[b] - shorts[a]) / max(len(shorts[b]), 1)
    turn.append((lt + stn))
avg_turn = np.mean(turn) if turn else 0.0

ls = ls.set_index("ym")
ls_gross = ls["ls_ret"]
ls_net = ls_gross - avg_turn * (COST_BPS/1e4)   # approx cost per rebalance

# ==================================================================
# 6. Metrics
# ==================================================================
def monthly_stats(r, rf=RF_ANNUAL):
    r = r.dropna()
    ann_ret = r.mean()*12
    ann_vol = r.std()*np.sqrt(12)
    sharpe = (ann_ret - rf)/ann_vol if ann_vol>0 else 0
    cum = (1+r).cumprod()
    mdd = (cum/cum.cummax()-1).min()
    hit = (r > 0).mean()
    return {"Ann Return %": ann_ret*100, "Ann Vol %": ann_vol*100,
            "Sharpe": sharpe, "MaxDD %": mdd*100, "Hit Rate %": hit*100}

print("="*70); print("MOMENTUM LONG-SHORT (Q5 long, Q1 short) — forward returns")
print("="*70)
res = pd.DataFrame({
    "Gross": monthly_stats(ls_gross),
    f"Net ({COST_BPS}bps)": monthly_stats(ls_net),
}).T
print(res.round(3).to_string())

print(f"\nAverage monthly turnover (both legs): {avg_turn:.2f}")
print("\n" + "="*70); print("INFORMATION COEFFICIENT (Spearman: momentum vs fwd return)")
print("="*70)
print(f"Mean IC        : {ic.mean():+.3f}")
print(f"IC IR (mean/sd): {ic.mean()/ic.std():+.3f}")
print(f"% months IC > 0: {(ic>0).mean()*100:.1f}%")

# ==================================================================
# 7. Charts
# ==================================================================
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
os.makedirs("charts", exist_ok=True)

cg = (1+ls_gross).cumprod(); cn = (1+ls_net).cumprod()
plt.figure(figsize=(9,5))
plt.plot(range(len(cg)), cg.values, label="Long-Short (gross)")
plt.plot(range(len(cn)), cn.values, label=f"Long-Short (net {COST_BPS}bps)")
plt.axhline(1, color="gray", lw=0.6)
plt.title("Momentum Long-Short: Cumulative Return"); plt.xlabel("Months")
plt.ylabel("Growth of 1"); plt.legend(); plt.grid(alpha=0.3)
plt.tight_layout(); plt.savefig("charts/momentum_ls.png", dpi=150); plt.close()

plt.figure(figsize=(9,4))
plt.bar(range(len(ic)), ic.values, color=["#55a868" if v>=0 else "#c44e52" for v in ic.values])
plt.axhline(ic.mean(), color="black", lw=1, ls="--", label=f"Mean IC {ic.mean():.3f}")
plt.title("Monthly Information Coefficient"); plt.xlabel("Months"); plt.ylabel("Spearman IC")
plt.legend(); plt.grid(alpha=0.3, axis="y")
plt.tight_layout(); plt.savefig("charts/ic.png", dpi=150); plt.close()

print("\nSaved charts/momentum_ls.png and charts/ic.png. Done.")
