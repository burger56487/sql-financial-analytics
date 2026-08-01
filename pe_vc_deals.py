# pe_vc_deals.py
# SQL-based SIMULATED PE/VC portfolio analytics database.
# Demonstrates schema design with constraints, JOINs, CTEs, window functions,
# and fund metrics (MOIC, DPI/RVPI/TVPI) on a fictional portfolio.
# NOTE: all data is simulated for demonstration.

import sqlite3
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 130)

# ==================================================================
# 1. Build database (foreign keys ON + CHECK constraints)
# ==================================================================
conn = sqlite3.connect(":memory:")
conn.execute("PRAGMA foreign_keys = ON;")   # SQLite needs this explicitly
cur = conn.cursor()

cur.executescript("""
DROP TABLE IF EXISTS deals;
DROP TABLE IF EXISTS companies;

CREATE TABLE companies (
    company_id   INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    sector       TEXT,
    country      TEXT,
    founded_year INTEGER
);

CREATE TABLE deals (
    deal_id           INTEGER PRIMARY KEY,
    company_id        INTEGER NOT NULL,
    fund              TEXT,
    stage             TEXT,
    invest_date       TEXT,
    invest_amount     REAL CHECK (invest_amount >= 0),          -- paid-in, USD m
    ownership_pct     REAL CHECK (ownership_pct >= 0 AND ownership_pct <= 100),
    status            TEXT CHECK (status IN ('Active','Exited','Written-off')),
    company_valuation REAL CHECK (company_valuation >= 0),       -- total company value, USD m
    valuation_date    TEXT,
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);
""")

companies = [
    (1,"NovaPay","Fintech","US",2018),(2,"MediSense","HealthTech","US",2017),
    (3,"DeepMindful","AI","UK",2019),(4,"GreenGrid","Climate","US",2016),
    (5,"ShopFlow","Consumer","SG",2018),(6,"DataForge","SaaS","US",2019),
    (7,"AgriNext","AgriTech","CN",2017),(8,"CloudNine","SaaS","US",2020),
    (9,"BioLeap","HealthTech","UK",2018),(10,"PayLink","Fintech","SG",2019),
    (11,"RoboLogix","AI","CN",2020),(12,"SolarWave","Climate","US",2017),
    (13,"EduSpark","EdTech","US",2019),(14,"FreshCart","Consumer","CN",2018),
    (15,"SecureNet","Cybersecurity","US",2016),(16,"VoxAI","AI","US",2021),
    (17,"HealthLoop","HealthTech","SG",2019),(18,"ChainTrust","Fintech","UK",2020),
    (19,"UrbanMove","Mobility","CN",2018),(20,"QuantEdge","Fintech","US",2019),
    (21,"NanoMed","HealthTech","US",2017),(22,"StreamlyAI","AI","US",2021),
    (23,"EcoPack","Climate","SG",2019),(24,"LoopCRM","SaaS","UK",2018),
]

# (deal_id, company_id, fund, stage, invest_date, invest_amount, ownership_pct,
#  status, company_valuation, valuation_date)
deals = [
    (1,1,"Fund I","Series B","2020-03-15",8.0,12.0,"Exited",2670.0,"2023-06-30"),
    (2,2,"Fund I","Series A","2019-06-01",4.0,15.0,"Active",147.0,"2023-12-31"),
    (3,3,"Fund I","Seed","2020-01-20",1.5,18.0,"Written-off",0.0,"2023-12-31"),
    (4,4,"Fund I","Series C","2019-09-10",12.0,8.0,"Active",375.0,"2023-12-31"),
    (5,5,"Fund I","Series A","2020-05-05",5.0,14.0,"Active",64.0,"2023-12-31"),
    (6,6,"Fund I","Series B","2021-02-12",10.0,10.0,"Active",260.0,"2023-12-31"),
    (7,7,"Fund I","Seed","2019-03-30",1.0,20.0,"Written-off",0.0,"2023-12-31"),
    (8,8,"Fund I","Series A","2021-07-01",6.0,13.0,"Active",108.0,"2023-12-31"),
    (9,9,"Fund I","Series B","2020-11-11",9.0,11.0,"Exited",573.0,"2023-03-15"),
    (10,10,"Fund I","Seed","2020-04-18",2.0,17.0,"Active",47.0,"2023-12-31"),
    (11,11,"Fund I","Series A","2021-01-25",7.0,12.0,"Active",42.0,"2023-12-31"),
    (12,12,"Fund I","Series C","2019-12-01",15.0,7.0,"Exited",643.0,"2022-09-01"),
    (13,13,"Fund II","Seed","2020-08-08",1.2,19.0,"Written-off",1.6,"2023-12-31"),
    (14,14,"Fund II","Series A","2020-02-14",5.0,15.0,"Active",73.0,"2023-12-31"),
    (15,15,"Fund II","Series B","2019-05-20",8.0,10.0,"Exited",1600.0,"2022-05-20"),
    (16,16,"Fund II","Seed","2022-03-01",2.5,16.0,"Active",75.0,"2023-12-31"),
    (17,17,"Fund II","Series A","2021-06-15",4.5,14.0,"Active",43.0,"2023-12-31"),
    (18,18,"Fund II","Seed","2021-09-09",1.8,18.0,"Written-off",0.0,"2023-12-31"),
    (19,19,"Fund II","Series B","2020-07-07",9.0,11.0,"Active",118.0,"2023-12-31"),
    (20,20,"Fund II","Series A","2020-10-30",6.0,13.0,"Active",262.0,"2023-12-31"),
    (21,21,"Fund II","Series C","2019-04-22",14.0,8.0,"Active",350.0,"2023-12-31"),
    (22,22,"Fund II","Seed","2022-01-10",3.0,15.0,"Active",120.0,"2023-12-31"),
    (23,23,"Fund II","Seed","2021-03-17",1.5,20.0,"Written-off",1.0,"2023-12-31"),
    (24,24,"Fund II","Series A","2019-11-05",5.0,14.0,"Exited",86.0,"2022-11-05"),
]

cur.executemany("INSERT INTO companies VALUES (?,?,?,?,?)", companies)
cur.executemany("INSERT INTO deals VALUES (?,?,?,?,?,?,?,?,?,?)", deals)
conn.commit()

def run(title, sql):
    print("\n" + "="*72); print(title); print("="*72)
    print(pd.read_sql(sql, conn).to_string(index=False))

# stake value = company_valuation * ownership_pct/100  (the fund's stake)
# MOIC = stake value / invested

# ==================================================================
# 2. Fund-level metrics: DPI / RVPI / TVPI (uses ownership properly)
# ==================================================================
run("Fund Metrics: paid-in, DPI, RVPI, TVPI", """
    SELECT
        ROUND(SUM(invest_amount),1) AS paid_in_m,
        ROUND(SUM(CASE WHEN status='Exited' THEN company_valuation*ownership_pct/100 END),1) AS realized_m,
        ROUND(SUM(CASE WHEN status='Active' THEN company_valuation*ownership_pct/100 END),1) AS unrealized_m,
        ROUND(SUM(CASE WHEN status='Exited' THEN company_valuation*ownership_pct/100 ELSE 0 END)
              / SUM(invest_amount),2) AS DPI,
        ROUND(SUM(CASE WHEN status='Active' THEN company_valuation*ownership_pct/100 ELSE 0 END)
              / SUM(invest_amount),2) AS RVPI,
        ROUND(SUM(company_valuation*ownership_pct/100) / SUM(invest_amount),2) AS TVPI
    FROM deals;
""")

run("By Fund (TVPI)", """
    SELECT fund,
           COUNT(*) AS deals,
           ROUND(SUM(invest_amount),1) AS paid_in_m,
           ROUND(SUM(company_valuation*ownership_pct/100),1) AS value_m,
           ROUND(SUM(company_valuation*ownership_pct/100)/SUM(invest_amount),2) AS TVPI
    FROM deals GROUP BY fund;
""")

# ==================================================================
# 3. Performance by sector / stage (stake value + MOIC)
# ==================================================================
run("Performance by Sector (JOIN + GROUP BY)", """
    SELECT c.sector,
           COUNT(*) AS deals,
           ROUND(SUM(d.invest_amount),1) AS invested_m,
           ROUND(SUM(d.company_valuation*d.ownership_pct/100),1) AS stake_value_m,
           ROUND(SUM(d.company_valuation*d.ownership_pct/100)/SUM(d.invest_amount),2) AS moic
    FROM deals d JOIN companies c ON c.company_id=d.company_id
    GROUP BY c.sector ORDER BY moic DESC;
""")

run("Performance by Stage", """
    SELECT stage, COUNT(*) AS deals,
           ROUND(SUM(invest_amount),1) AS invested_m,
           ROUND(SUM(company_valuation*ownership_pct/100)/SUM(invest_amount),2) AS moic
    FROM deals GROUP BY stage ORDER BY moic DESC;
""")

# ==================================================================
# 4. Realized / Unrealized / Written-off (3 categories, CASE)
# ==================================================================
run("Status Breakdown (3 categories)", """
    SELECT status,
           COUNT(*) AS deals,
           ROUND(SUM(invest_amount),1) AS invested_m,
           ROUND(SUM(company_valuation*ownership_pct/100),1) AS stake_value_m,
           ROUND(SUM(company_valuation*ownership_pct/100)/SUM(invest_amount),2) AS moic
    FROM deals GROUP BY status ORDER BY stake_value_m DESC;
""")

# ==================================================================
# 5. Top deals by MOIC (window RANK)
# ==================================================================
run("Top 5 Deals by MOIC", """
    SELECT name, sector, stage, invested_m, stake_value_m, moic FROM (
        SELECT c.name, c.sector, d.stage,
               d.invest_amount AS invested_m,
               ROUND(d.company_valuation*d.ownership_pct/100,1) AS stake_value_m,
               ROUND(d.company_valuation*d.ownership_pct/100/d.invest_amount,1) AS moic,
               RANK() OVER (ORDER BY d.company_valuation*d.ownership_pct/100/d.invest_amount DESC) AS rk
        FROM deals d JOIN companies c ON c.company_id=d.company_id)
    WHERE rk<=5 ORDER BY moic DESC;
""")

# ==================================================================
# 6. Vintage analysis (with average holding years)
# ==================================================================
run("Vintage Year Analysis (invested, MOIC, avg holding yrs)", """
    SELECT strftime('%Y', invest_date) AS vintage,
           COUNT(*) AS deals,
           ROUND(SUM(invest_amount),1) AS invested_m,
           ROUND(SUM(company_valuation*ownership_pct/100)/SUM(invest_amount),2) AS moic,
           ROUND(AVG((julianday(valuation_date)-julianday(invest_date))/365.25),1) AS avg_hold_yrs
    FROM deals GROUP BY vintage ORDER BY vintage;
""")

# ==================================================================
# 7. GAIN (profit) concentration — uses profit, not raw value (CTE)
# ==================================================================
run("Gain (Profit) Concentration — top 3 share of total gains", """
    WITH gains AS (
        SELECT c.name,
               d.company_valuation*d.ownership_pct/100 - d.invest_amount AS gain
        FROM deals d JOIN companies c ON c.company_id=d.company_id),
    ranked AS (
        SELECT name, gain,
               RANK() OVER (ORDER BY gain DESC) AS rk,
               SUM(CASE WHEN gain>0 THEN gain ELSE 0 END) OVER () AS total_gain
        FROM gains)
    SELECT name, ROUND(gain,1) AS gain_m,
           ROUND(100.0*gain/total_gain,1) AS pct_of_total_gains
    FROM ranked WHERE rk<=3 ORDER BY gain_m DESC;
""")

# ==================================================================
# 8. Gross annualized return (IRR proxy) per deal — pandas step
# ==================================================================
d = pd.read_sql("""
    SELECT c.name,
           d.invest_amount AS invested,
           d.company_valuation*d.ownership_pct/100 AS stake_value,
           (julianday(d.valuation_date)-julianday(d.invest_date))/365.25 AS years
    FROM deals d JOIN companies c ON c.company_id=d.company_id
    WHERE d.company_valuation*d.ownership_pct/100 > 0 AND
          (julianday(d.valuation_date)-julianday(d.invest_date)) > 0;
""", conn)
d["moic"] = d["stake_value"]/d["invested"]
d["gross_irr_%"] = ((d["moic"]**(1/d["years"]) - 1)*100).round(1)
print("\n" + "="*72); print("Gross Annualized Return (IRR proxy) — top 5"); print("="*72)
print(d.sort_values("gross_irr_%", ascending=False).head(5)
        [["name","invested","stake_value","years","moic","gross_irr_%"]].round(2).to_string(index=False))

# ==================================================================
# 9. Charts
# ==================================================================
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
os.makedirs("charts", exist_ok=True)

df_sec = pd.read_sql("""
    SELECT c.sector, ROUND(SUM(d.company_valuation*d.ownership_pct/100)/SUM(d.invest_amount),2) AS moic
    FROM deals d JOIN companies c ON c.company_id=d.company_id
    GROUP BY c.sector ORDER BY moic DESC;""", conn)
plt.figure(figsize=(9,5))
plt.bar(df_sec["sector"], df_sec["moic"], color="#4c72b0")
plt.title("MOIC by Sector"); plt.ylabel("MOIC (x)"); plt.xticks(rotation=45, ha="right")
plt.tight_layout(); plt.savefig("charts/moic_by_sector.png", dpi=150); plt.close()

df_g = pd.read_sql("""
    WITH gains AS (SELECT c.name, d.company_valuation*d.ownership_pct/100 - d.invest_amount AS gain
                   FROM deals d JOIN companies c ON c.company_id=d.company_id),
    ranked AS (SELECT name, gain, RANK() OVER (ORDER BY gain DESC) AS rk,
               SUM(CASE WHEN gain>0 THEN gain ELSE 0 END) OVER () AS tot FROM gains)
    SELECT name, ROUND(100.0*gain/tot,1) AS pct FROM ranked WHERE rk<=5 ORDER BY pct DESC;""", conn)
plt.figure(figsize=(8,5))
plt.bar(df_g["name"], df_g["pct"], color="#dd8452")
plt.title("Gain Concentration — Top 5 Deals (% of total profit)")
plt.ylabel("% of total gains"); plt.xticks(rotation=30, ha="right")
plt.tight_layout(); plt.savefig("charts/gain_concentration.png", dpi=150); plt.close()

conn.close()
print("\nSaved charts. Done.")
