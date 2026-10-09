import time
from app.db.session import SessionLocal
from app.dataset.builder import ModelingDatasetBuilder

db = SessionLocal()
builder = ModelingDatasetBuilder(db)
t0 = time.time()
ds = builder.build_sprint_4_5_dataset()
t1 = time.time()
print(f"Loaded dataset in {t1 - t0:.2f} seconds.")
print(f"Dev rows: {len(ds.development_rows)}, Holdout rows: {len(ds.holdout_rows)}")
print(f"Dynamic recomputations: {ds.metadata.get('dynamic_computations', 0)}")
