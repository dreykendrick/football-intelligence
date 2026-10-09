import sqlite3
import json

conn = sqlite3.connect('c:/Users/kibaj/FB/backend/football_dev.db')
c = conn.cursor()

for t in ['feature_definitions', 'feature_sets', 'feature_snapshots']:
    c.execute(f"PRAGMA table_info({t});")
    cols = [r[1] for r in c.fetchall()]
    print(f"\n{t} columns ({len(cols)}):", cols)

    c.execute(f"SELECT * FROM {t} LIMIT 1")
    row = c.fetchone()
    if row:
        d = dict(zip(cols, row))
        if 'feature_document' in d:
            doc = json.loads(d['feature_document'])
            print("  feature_document keys count:", len(doc.keys()))
            print("  feature_document sample keys:", list(doc.keys())[:20])
        elif 'snapshot_document' in d:
            doc = json.loads(d['snapshot_document'])
            print("  snapshot_document keys count:", len(doc.keys()))
            print("  snapshot_document sample keys:", list(doc.keys())[:20])
        else:
            for k in list(d.keys())[:5]:
                print(f"  {k}: {d[k]}")
