import os
import sys
import subprocess
import time
from sqlalchemy import create_engine
from app.db.session import SessionLocal
from app.db.models import FeatureSnapshot

def run():
    print("===========================================")
    print(" STARTING FULL 4,338 MATCH MATERIALIZATION ")
    print("===========================================")
    
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, "-u", "app/features/cli.py", "build", "--dataset", "mvp_a_historical_v1"],
        cwd="C:/Users/kibaj/FB/backend",
        capture_output=True,
        text=True
    )
    t1 = time.time()
    
    print(f"Build Finished in {t1 - t0:.2f} seconds.")
    print("STDOUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
        
    print("\n===========================================")
    print(" RUNNING MISSINGNESS AUDIT & CACHE AUDIT")
    print("===========================================")
    db = SessionLocal()
    count = db.query(FeatureSnapshot).count()
    print(f"Total Snapshots in DB: {count}")
    
    result2 = subprocess.run(
        [sys.executable, "-u", "app/features/cli.py", "report", "--dataset", "mvp_a_historical_v1"],
        cwd="C:/Users/kibaj/FB/backend",
        capture_output=True,
        text=True
    )
    print(result2.stdout)
    
    print("\n===========================================")
    print(" RUNNING SPRINT 4.5 SMOKE TEST")
    print("===========================================")
    result3 = subprocess.run(
        [sys.executable, "-u", "scratch/sprint_4_5_eval.py", "--smoke-test"],
        cwd="C:/Users/kibaj/FB/backend",
        capture_output=True,
        text=True
    )
    print(result3.stdout)
    if result3.stderr:
        print(result3.stderr)
        
    print("ALL DONE.")

if __name__ == "__main__":
    run()
