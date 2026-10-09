import sys
import os
sys.path.append('c:/Users/kibaj/FB/backend')

from app.db.session import SessionLocal
from app.models.builder import ModelingDatasetBuilder

db = SessionLocal()
try:
    builder = ModelingDatasetBuilder(enforce_readiness_gate=False)
    manifest, rows = builder.build_modeling_dataset(db, limit=5)
    print("Fetched", len(rows), "rows")
    if rows:
        print("Feature count per row:", len(rows[0].ordered_feature_names))
        print("Sample features:", rows[0].ordered_feature_names[:20])
except Exception as e:
    print("Error:", str(e))
finally:
    db.close()
