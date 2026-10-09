"""
Deterministic Dataset Release Fingerprint Calculator
Computes reproducible 64-character SHA-256 fingerprints based strictly on immutable scientific content.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


class DatasetFingerprintCalculator:
    """Calculates deterministic SHA-256 fingerprints for historical dataset releases."""

    @staticmethod
    def compute_fingerprint(
        key: str,
        version: str,
        selection_policy_key: str,
        selection_policy_version: str,
        seasons_data: list[dict[str, Any]],
        matches_data: list[dict[str, Any]],
    ) -> str:
        """
        Computes SHA-256 hash over canonical scientific elements.
        Volatile fields (build timestamp, database surrogate primary keys, log IDs) are explicitly omitted.
        """
        # 1. Canonical Season Tuples sorted by (competition_code, season_year)
        sorted_seasons = sorted(
            [
                {
                    "competition_code": s["competition_code"],
                    "season_year": s["season_year"],
                    "source_checksum": s.get("source_checksum") or "",
                }
                for s in seasons_data
            ],
            key=lambda x: (x["competition_code"], x["season_year"]),
        )

        # 2. Canonical Match Tuples sorted by (kickoff_iso, home_team_id, away_team_id, match_id)
        sorted_matches = sorted(
            [
                {
                    "match_id": str(m["match_id"]),
                    "kickoff_utc": m["kickoff_utc"].isoformat() if isinstance(m["kickoff_utc"], datetime) else str(m["kickoff_utc"]),
                    "home_team_id": str(m["home_team_id"]),
                    "away_team_id": str(m["away_team_id"]),
                    "home_score": m.get("home_score"),
                    "away_score": m.get("away_score"),
                    "raw_source_checksum": m.get("raw_source_checksum") or "",
                }
                for m in matches_data
            ],
            key=lambda x: (x["kickoff_utc"], x["home_team_id"], x["away_team_id"], x["match_id"]),
        )

        # 3. Payload serialization
        canonical_payload = {
            "key": key,
            "version": version,
            "selection_policy_key": selection_policy_key,
            "selection_policy_version": selection_policy_version,
            "seasons": sorted_seasons,
            "matches": sorted_matches,
        }

        serialized = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def compute_release_fingerprint(cls, db: Any, release: Any) -> str:
        """Computes SHA-256 fingerprint for an existing DB release instance."""
        from app.db.models import HistoricalDatasetMatch, HistoricalDatasetSeason, Match

        seasons = db.query(HistoricalDatasetSeason).filter_by(dataset_release_id=release.id).all()
        dataset_matches = db.query(HistoricalDatasetMatch).filter_by(dataset_release_id=release.id).all()
        match_ids = [m.match_id for m in dataset_matches]
        matches = db.query(Match).filter(Match.id.in_(match_ids)).all() if match_ids else []
        match_by_id = {m.id: m for m in matches}

        seasons_data = [
            {
                "competition_code": s.competition_code,
                "season_year": s.season_year,
                "source_checksum": s.source_checksum,
            }
            for s in seasons
        ]
        matches_data = [
            {
                "match_id": m.match_id,
                "kickoff_utc": m.kickoff_utc,
                "home_team_id": m.home_team_id,
                "away_team_id": m.away_team_id,
                "home_score": match_by_id[m.match_id].home_score if m.match_id in match_by_id else None,
                "away_score": match_by_id[m.match_id].away_score if m.match_id in match_by_id else None,
                "raw_source_checksum": m.raw_source_checksum,
            }
            for m in dataset_matches
        ]

        return cls.compute_fingerprint(
            key=release.key,
            version=release.version,
            selection_policy_key=release.selection_policy_key,
            selection_policy_version=release.selection_policy_version,
            seasons_data=seasons_data,
            matches_data=matches_data,
        )
