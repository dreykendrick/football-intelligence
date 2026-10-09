import sys, os
sys.path.append('c:/Users/kibaj/FB/backend')
from app.db.session import SessionLocal
from app.models.builder import ModelingDatasetBuilder
import numpy as np

db = SessionLocal()
try:
    print("Loading dataset...")
    builder = ModelingDatasetBuilder(dataset_key="mvp_a_historical_v1", version="v1")
    manifest, rows = builder.build_modeling_dataset(db, limit=None)
    print("Total rows:", len(rows))
    
    if not rows:
        sys.exit(1)
        
    all_features = rows[0].ordered_feature_names
    print("Total features available:", len(all_features))
    
    # Analyze missingness
    n_rows = len(rows)
    feature_matrix = []
    for r in rows:
        feature_matrix.append(r.feature_values)
        
    feature_matrix = np.array(feature_matrix, dtype=np.float64)
    missing_rates = np.isnan(feature_matrix).mean(axis=0)
    
    const_feats = []
    high_missing_feats = []
    usable_numeric = []
    
    for i, fname in enumerate(all_features):
        col = feature_matrix[:, i]
        mrate = missing_rates[i]
        
        if mrate > 0.5:
            high_missing_feats.append(fname)
            continue
            
        valid = col[~np.isnan(col)]
        if len(valid) == 0:
            const_feats.append(fname)
            continue
            
        if np.var(valid) < 1e-9:
            const_feats.append(fname)
            continue
            
        usable_numeric.append(fname)
        
    print(f"High missingness (>50%): {len(high_missing_feats)}")
    print(f"Constant / Zero variance: {len(const_feats)}")
    print(f"Usable numeric features: {len(usable_numeric)}")
    
    print("\nSample usable features:", usable_numeric[:10])
    
finally:
    db.close()
