import os
import sys
import subprocess
import time
import json
from uuid import UUID
from datetime import datetime
from sqlalchemy import create_engine
from app.db.session import SessionLocal
from app.db.models import FeatureSnapshot, Match
from app.dataset.query import HistoricalDatasetQueryService

def get_db_size():
    db_path = "app/db/football_intelligence.db"
    return os.path.getsize(db_path) if os.path.exists(db_path) else 0

def run_verification():
    db = SessionLocal()
    print("========================================")
    print(" SPRINT 4.5A VERIFICATION RUNNER")
    print("========================================")
    
    size_before = get_db_size()
    print(f"DB Size Before: {size_before / 1024 / 1024:.2f} MB")
    
    # 1. Full Build
    print("\n--- 1. RUNNING FULL MATERIALIZATION ---")
    t0 = time.time()
    res1 = subprocess.run(
        [sys.executable, "-u", "app/features/cli.py", "build", "--dataset", "mvp_a_historical_v1"],
    )
    t1 = time.time()
    print(f"Build completed in {t1 - t0:.2f} seconds.")
    if res1.returncode != 0:
        print("BUILD FAILED!")
        return
        
    size_after = get_db_size()
    
    # 2. Cache Audit
    print("\n--- 2. CACHE COMPLETENESS AUDIT ---")
    count = db.query(FeatureSnapshot).count()
    expected = db.query(Match).count()
    print(f"Expected: {expected}, Snapshots: {count}")
    
    subprocess.run(
        [sys.executable, "-u", "app/features/cli.py", "report", "--dataset", "mvp_a_historical_v1"],
    )
        
    # 3. Parity Test (we can run parity_check.py but expanded)
    print("\n--- 3. RUNNING EXPANDED PARITY TEST ---")
    with open("scratch/parity_check_expanded.py", "w") as f:
        f.write('''import sys
import time
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.features.assembler import FeatureSetAssembler
from app.db.models import FeatureSnapshot
from app.dataset.query import HistoricalDatasetQueryService

def parity_check():
    db = SessionLocal()
    assembler = FeatureSetAssembler()
    query_service = HistoricalDatasetQueryService(db)
    
    # Take 80 matches across different leagues
    matches = query_service.get_dataset_matches(dataset_key="mvp_a_historical_v1", version="v1", approved_only=True)
    selected = matches[:20] + matches[500:520] + matches[1000:1020] + matches[2000:2020]
    
    mismatches = 0
    total_features = 0
    max_diff = 0.0
    fp_mismatch = 0
    
    print(f"Running Parity Check for {len(selected)} fixtures...")
    for m in selected:
        dto = assembler.assemble_feature_vector_for_match(
            db, m.id, cutoff_timestamp=m.kickoff_utc
        )
        snap = db.query(FeatureSnapshot).filter_by(match_id=m.id, snapshot_type="FINAL").first()
        if not snap:
            print(f"No snapshot for {m.id}")
            continue
            
        for fkey, old_val in dto.feature_vector_dict.items():
            total_features += 1
            new_val = snap.feature_values.get(fkey)
            if old_val is None and new_val is None:
                continue
            if isinstance(old_val, float):
                diff = abs(old_val - new_val)
                if diff > max_diff: max_diff = diff
                if diff > 1e-5: mismatches += 1
            else:
                if old_val != new_val: mismatches += 1
                    
        if dto.snapshot_fingerprint != snap.data_quality_metadata.get("fingerprint_sha256"):
            fp_mismatch += 1

    print(f"Fixtures compared: {len(selected)}")
    print(f"Features compared: {total_features}")
    print(f"Mismatches: {mismatches}")
    print(f"Fingerprint Mismatches: {fp_mismatch}")
    print(f"Max Numeric Difference: {max_diff}")

if __name__ == "__main__":
    parity_check()
''')
    res3 = subprocess.run([sys.executable, "scratch/parity_check_expanded.py"])
    
    # 4. Idempotency Run
    print("\n--- 4. IDEMPOTENCY / SECOND RUN ---")
    t0_idem = time.time()
    res4 = subprocess.run(
        [sys.executable, "-u", "app/features/cli.py", "build", "--dataset", "mvp_a_historical_v1"],
    )
    t1_idem = time.time()
    print(f"Second build completed in {t1_idem - t0_idem:.2f} seconds.")
    
    # 5. Dataset Load Bench
    print("\n--- 5. DATASET LOAD BENCHMARK ---")
    with open("scratch/bench_load.py", "w") as f:
        f.write('''import time
from app.db.session import SessionLocal
from app.models.builder import ModelingDatasetBuilder

db = SessionLocal()
builder = ModelingDatasetBuilder(db)
t0 = time.time()
ds = builder.build_sprint_4_5_dataset()
t1 = time.time()
print(f"Loaded dataset in {t1 - t0:.2f} seconds.")
print(f"Dev rows: {len(ds.development_rows)}, Holdout rows: {len(ds.holdout_rows)}")
print(f"Dynamic recomputations: {ds.metadata.get('dynamic_computations', 0)}")
''')
    res5 = subprocess.run([sys.executable, "scratch/bench_load.py"])
    
    # 6. Evaluator Smoke Test
    print("\n--- 6. EVALUATOR SMOKE TEST ---")
    res6 = subprocess.run([sys.executable, "scratch/sprint_4_5_eval.py", "--smoke-test"])
    
    # 7. Test Suite
    print("\n--- 7. REGRESSION SUITE ---")
    res7 = subprocess.run(["pytest", "-q"])
    
    print("\n========================================")
    print(" VERIFICATION COMPLETE")
    print(f"DB Size After: {size_after / 1024 / 1024:.2f} MB")
    print("========================================")

if __name__ == "__main__":
    run_verification()
