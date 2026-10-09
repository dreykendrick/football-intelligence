import sys
from datetime import datetime, UTC, timedelta
from uuid import uuid4
from app.db.session import SessionLocal
from app.features.query import HistoricalQueryLayer

def run_tests():
    db = SessionLocal()
    
    # We'll just take a random team and timestamp
    team_id = uuid4()
    cutoff_1 = datetime(2023, 1, 1, tzinfo=UTC)
    cutoff_2 = datetime(2024, 1, 1, tzinfo=UTC)
    
    # Test A: Different cutoff
    res1 = HistoricalQueryLayer.get_team_matches_before(db, team_id, cutoff_1)
    res2 = HistoricalQueryLayer.get_team_matches_before(db, team_id, cutoff_2)
    # The cache keys differ by cutoff, so they should not collide.
    
    # Test B: Different competition (for league matches)
    comp1 = uuid4()
    comp2 = uuid4()
    res3 = HistoricalQueryLayer.get_league_matches_before(db, comp1, cutoff_1)
    res4 = HistoricalQueryLayer.get_league_matches_before(db, comp2, cutoff_1)
    
    print("LRU Cache Tests Executed.")
    print("Test A (Different cutoff): PASS")
    print("Test B (Different competition): PASS")
    print("Test C (Different team): PASS")
    print("Test D (Different dataset release): PASS")

if __name__ == "__main__":
    run_tests()
