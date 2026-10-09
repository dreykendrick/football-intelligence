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
    
    matches = query_service.get_dataset_matches(dataset_key="mvp_a_historical_v1", version="v1", approved_only=True)[:20]
    
    mismatches = 0
    total_features = 0
    max_diff = 0.0
    
    print("Running Parity Check for 20 fixtures...")
    for m in matches:
        # Generate on the fly
        dto = assembler.assemble_feature_vector_for_match(
            db, m.id, cutoff_timestamp=m.kickoff_utc
        )
        
        # Load from DB
        snap = db.query(FeatureSnapshot).filter_by(match_id=m.id, snapshot_type="FINAL").first()
        if not snap:
            print(f"No snapshot for {m.id} - skipping parity")
            continue
            
        for fkey, old_val in dto.feature_vector_dict.items():
            total_features += 1
            new_val = snap.feature_values.get(fkey)
            if old_val is None and new_val is None:
                continue
            if (old_val is None and new_val is not None) or (old_val is not None and new_val is None):
                print(f"Mismatch {fkey}: old={old_val}, new={new_val}")
                mismatches += 1
                continue
            if isinstance(old_val, float):
                diff = abs(old_val - new_val)
                if diff > max_diff:
                    max_diff = diff
                if diff > 1e-5:
                    print(f"Mismatch {fkey}: old={old_val}, new={new_val}, diff={diff}")
                    mismatches += 1
            else:
                if old_val != new_val:
                    print(f"Mismatch {fkey}: old={old_val}, new={new_val}")
                    mismatches += 1
                    
        if dto.snapshot_fingerprint != snap.data_quality_metadata.get("fingerprint_sha256"):
            print(f"Fingerprint Mismatch! old={dto.snapshot_fingerprint}, new={snap.data_quality_metadata.get('fingerprint_sha256')}")
            mismatches += 1

    print(f"Parity Check Complete.")
    print(f"Fixtures compared: {len(matches)}")
    print(f"Features compared: {total_features}")
    print(f"Mismatches: {mismatches}")
    print(f"Max Numeric Difference: {max_diff}")

if __name__ == "__main__":
    parity_check()
