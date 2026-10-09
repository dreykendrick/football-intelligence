import sqlite3
import json

conn = sqlite3.connect('c:/Users/kibaj/FB/backend/football_dev.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [t[0] for t in c.fetchall()]
print('Tables:', tables)

for t in ['features', 'match_features', 'dataset_releases']:
    if t in tables:
        c.execute(f"PRAGMA table_info({t});")
        cols = [r[1] for r in c.fetchall()]
        print(f"{t} columns ({len(cols)}):", cols[:20])

        c.execute(f"SELECT * FROM {t} LIMIT 1")
        row = c.fetchone()
        if row:
            d = dict(zip(cols, row))
            # print samples
            for k in list(d.keys())[:5]:
                print(f"  {k}: {d[k]}")
