import sys
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
