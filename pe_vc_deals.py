# pe_vc_deals.py
# A PE/VC deal database built with SQL (SQLite), demonstrating
# schema design, JOINs, aggregations, window functions and CTEs.

import sqlite3
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 120)

# ==================================================================
# 1. Build database
# ==================================================================
conn = sqlite3.connect(":memory:")   # in-memory; use "deals.db" to persist
cur = conn.cursor()

cur.executescript("""
DROP TABLE IF EXISTS companies;
DROP TABLE IF EXISTS deals;

CREATE TABLE companies (
    company_id   INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    sector       TEXT,
    country      TEXT,
    founded_year INTEGER
);

CREATE TABLE deals (
    deal_id       INTEGER PRIMARY KEY,
    company_id    INTEGER,
    stage         TEXT,
    invest_date   TEXT,
    invest_amount REAL,      -- USD millions
    ownership_pct REAL,
    status        TEXT,      -- Active / Exited / Written-off
    value         REAL,      -- current mark or exit value (USD millions)
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);
""")

# ---- sample data (fictional VC portfolio with power-law outcomes) ----
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

# deal: (deal_id, company_id, stage, invest_date, invest_amount, ownership_pct, status, value)
deals = [
    (1,1,"Series B","2020-03-15",8.0,12.0,"Exited",320.0),      # 40x winner
    (2,2,"Series A","2019-06-01",4.0,15.0,"Active",22.0),
    (3,3,"Seed","2020-01-20",1.5,18.0,"Written-off",0.0),
    (4,4,"Series C","2019-09-10",12.0,8.0,"Active",30.0),
    (5,5,"Series A","2020-05-05",5.0,14.0,"Active",9.0),
    (6,6,"Series B","2021-02-12",10.0,10.0,"Active",26.0),
    (7,7,"Seed","2019-03-30",1.0,20.0,"Written-off",0.0),
    (8,8,"Series A","2021-07-01",6.0,13.0,"Active",14.0),
    (9,9,"Series B","2020-11-11",9.0,11.0,"Exited",63.0),        # 7x
    (10,10,"Seed","2020-04-18",2.0,17.0,"Active",8.0),
    (11,11,"Series A","2021-01-25",7.0,12.0,"Active",5.0),
    (12,12,"Series C","2019-12-01",15.0,7.0,"Exited",45.0),
    (13,13,"Seed","2020-08-08",1.2,19.0,"Written-off",0.3),
    (14,14,"Series A","2020-02-14",5.0,15.0,"Active",11.0),
    (15,15,"Series B","2019-05-20",8.0,10.0,"Exited",160.0),      # 20x
    (16,16,"Seed","2022-03-01",2.5,16.0,"Active",12.0),
    (17,17,"Series A","2021-06-15",4.5,14.0,"Active",6.0),
    (18,18,"Seed","2021-09-09",1.8,18.0,"Written-off",0.0),
    (19,19,"Series B","2020-07-07",9.0,11.0,"Active",13.0),
    (20,20,"Series A","2020-10-30",6.0,13.0,"Active",34.0),       # strong mark
    (21,21,"Series C","2019-04-22",14.0,8.0,"Active",28.0),
    (22,22,"Seed","2022-01-10",3.0,15.0,"Active",18.0),
    (23,23,"Seed","2021-03-17",1.5,20.0,"Written-off",0.2),
    (24,24,"Series A","2019-11-05",5.0,14.0,"Exited",12.0),
]

cur.executemany("INSERT INTO companies VALUES (?,?,?,?,?)", companies)
cur.executemany("INSERT INTO deals VALUES (?,?,?,?,?,?,?,?)", deals)
conn.commit()

def run(title, sql):
    print("\n" + "="*70)
    print(title)
    print("="*70)
    print(pd.read_sql(sql, conn).to_string(index=False))

# ==================================================================
# 2. Analytical SQL queries
# ==================================================================

run("Portfolio Overview (total invested, value, MOIC)", """
    SELECT
        ROUND(SUM(invest_amount),1)              AS invested_m,
        ROUND(SUM(value),1)                      AS value_m,
        ROUND(SUM(value)*1.0/SUM(invest_amount),2) AS moic,
        COUNT(*)                                 AS num_deals
    FROM deals;
""")

run("Performance by Sector (JOIN + GROUP BY)", """
    SELECT
        c.sector,
        COUNT(*)                                    AS deals,
        ROUND(SUM(d.invest_amount),1)               AS invested_m,
        ROUND(SUM(d.value),1)                       AS value_m,
        ROUND(SUM(d.value)*1.0/SUM(d.invest_amount),2) AS moic
    FROM deals d
    JOIN companies c ON c.company_id = d.company_id
    GROUP BY c.sector
    ORDER BY moic DESC;
""")

run("Performance by Stage", """
    SELECT stage,
           COUNT(*) AS deals,
           ROUND(SUM(invest_amount),1) AS invested_m,
           ROUND(SUM(value)*1.0/SUM(invest_amount),2) AS moic
    FROM deals
    GROUP BY stage
    ORDER BY moic DESC;
""")

run("Realized vs Unrealized (CASE + GROUP BY)", """
    SELECT
        CASE WHEN status='Exited' THEN 'Realized' ELSE 'Unrealized' END AS bucket,
        COUNT(*) AS deals,
        ROUND(SUM(invest_amount),1) AS invested_m,
        ROUND(SUM(value),1) AS value_m,
        ROUND(SUM(value)*1.0/SUM(invest_amount),2) AS moic
    FROM deals
    GROUP BY bucket;
""")

run("Top 5 Deals by MOIC (window RANK)", """
    SELECT name, sector, stage, invest_amount AS invested_m, value AS value_m, moic
    FROM (
        SELECT c.name, c.sector, d.stage, d.invest_amount, d.value,
               ROUND(d.value*1.0/d.invest_amount,1) AS moic,
               RANK() OVER (ORDER BY d.value*1.0/d.invest_amount DESC) AS rk
        FROM deals d JOIN companies c ON c.company_id=d.company_id
    )
    WHERE rk <= 5
    ORDER BY moic DESC;
""")

run("Vintage Year Analysis (invested by year)", """
    SELECT strftime('%Y', invest_date) AS vintage,
           COUNT(*) AS deals,
           ROUND(SUM(invest_amount),1) AS invested_m,
           ROUND(SUM(value)*1.0/SUM(invest_amount),2) AS moic
    FROM deals
    GROUP BY vintage
    ORDER BY vintage;
""")

run("Win/Loss Distribution (CASE buckets)", """
    SELECT
        CASE
            WHEN value*1.0/invest_amount >= 3 THEN 'Winner (>=3x)'
            WHEN value*1.0/invest_amount >= 1 THEN 'Moderate (1-3x)'
            ELSE 'Loss (<1x)'
        END AS outcome,
        COUNT(*) AS deals,
        ROUND(SUM(value),1) AS value_m
    FROM deals
    GROUP BY outcome
    ORDER BY value_m DESC;
""")

run("Return Concentration (CTE: top 3 share of total value)", """
    WITH ranked AS (
        SELECT c.name, d.value,
               RANK() OVER (ORDER BY d.value DESC) AS rk,
               SUM(d.value) OVER () AS total_value
        FROM deals d JOIN companies c ON c.company_id=d.company_id
    )
    SELECT name,
           ROUND(value,1) AS value_m,
           ROUND(100.0*value/total_value,1) AS pct_of_total
    FROM ranked
    WHERE rk <= 3
    ORDER BY value_m DESC;
""")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
os.makedirs("charts", exist_ok=True)


df_sec = pd.read_sql("""
    SELECT c.sector, ROUND(SUM(d.value)*1.0/SUM(d.invest_amount),2) AS moic
    FROM deals d JOIN companies c ON c.company_id=d.company_id
    GROUP BY c.sector ORDER BY moic DESC;
""", conn)
plt.figure(figsize=(9,5))
plt.bar(df_sec["sector"], df_sec["moic"], color="#4c72b0")
plt.title("MOIC by Sector"); plt.ylabel("MOIC (x)"); plt.xticks(rotation=45, ha="right")
plt.tight_layout(); plt.savefig("charts/moic_by_sector.png", dpi=150); plt.close()


df_conc = pd.read_sql("""
    WITH ranked AS (
        SELECT c.name, d.value, RANK() OVER (ORDER BY d.value DESC) AS rk,
               SUM(d.value) OVER () AS tot
        FROM deals d JOIN companies c ON c.company_id=d.company_id)
    SELECT name, ROUND(100.0*value/tot,1) AS pct FROM ranked WHERE rk<=5 ORDER BY pct DESC;
""", conn)
plt.figure(figsize=(8,5))
plt.bar(df_conc["name"], df_conc["pct"], color="#dd8452")
plt.title("Return Concentration — Top 5 Deals (% of Portfolio Value)")
plt.ylabel("% of total value"); plt.xticks(rotation=30, ha="right")
plt.tight_layout(); plt.savefig("charts/concentration.png", dpi=150); plt.close()

print("Saved charts to charts/")


conn.close()
print("\nDone.")
