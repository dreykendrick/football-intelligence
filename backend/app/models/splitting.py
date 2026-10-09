"""
Temporal Split Architecture & Chronological Evaluation Framework
Implements expanding-window, season-based holdout, and competition-aware temporal dataset splitters.
Guarantees strict forward-chaining chronology, zero partition overlap, and serializable split manifests.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from app.models.dataset_dto import ModelingRowDTO


class TemporalSplitStrategy(str, Enum):
    EXPANDING_WINDOW = "EXPANDING_WINDOW"
    SEASON_HOLDOUT = "SEASON_HOLDOUT"
    COMPETITION_TEMPORAL = "COMPETITION_TEMPORAL"


class TemporalSplitPartition(BaseModel):
    """Metadata and match IDs for a single fold's Train/Validation/Test partition."""

    fold_id: int
    train_start: str | None = None
    train_end: str | None = None
    train_count: int = 0
    val_start: str | None = None
    val_end: str | None = None
    val_count: int = 0
    test_start: str | None = None
    test_end: str | None = None
    test_count: int = 0
    competitions: list[str] = Field(default_factory=list)
    train_match_ids: list[str] = Field(default_factory=list)
    val_match_ids: list[str] = Field(default_factory=list)
    test_match_ids: list[str] = Field(default_factory=list)


class TemporalSplitManifest(BaseModel):
    """Immutable, serializable manifest detailing the temporal evaluation structure."""

    manifest_id: str = Field(default_factory=lambda: str(uuid4()))
    strategy: TemporalSplitStrategy
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    dataset_release_key: str = "mvp_a_historical:v1"
    dataset_release_fingerprint: str = ""
    feature_set_key: str = "mvp_a_feature_set_v1"
    total_rows_evaluated: int = 0
    folds: list[TemporalSplitPartition] = Field(default_factory=list)
    config_fingerprint: str = ""

    def compute_fingerprint(self) -> str:
        """Computes deterministic SHA-256 fingerprint of the split partition layout."""
        fold_summaries = [
            f"fold_{f.fold_id}:tr={f.train_count}:val={f.val_count}:te={f.test_count}:"
            f"tr_s={f.train_start}:tr_e={f.train_end}:te_s={f.test_start}:te_e={f.test_end}"
            for f in self.folds
        ]
        raw = f"{self.strategy.value}:{self.dataset_release_key}:{self.feature_set_key}:{':'.join(fold_summaries)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def validate_temporal_partition_invariants(
    train_rows: list[ModelingRowDTO],
    val_rows: list[ModelingRowDTO],
    test_rows: list[ModelingRowDTO],
    allow_empty_val: bool = False,
    allow_empty_test: bool = False,
) -> None:
    """
    Strictly asserts that:
    1. Training set is non-empty.
    2. No match appears in multiple partitions.
    3. Chronology: max(train.kickoff) <= min(val.kickoff) <= min(test.kickoff).
    """
    if not train_rows:
        raise ValueError("TEMPORAL SPLIT VIOLATION: Training partition cannot be empty.")

    if not allow_empty_val and not val_rows:
        raise ValueError("TEMPORAL SPLIT VIOLATION: Validation partition cannot be empty.")

    if not allow_empty_test and not test_rows:
        raise ValueError("TEMPORAL SPLIT VIOLATION: Test partition cannot be empty.")

    train_ids = {r.match_id for r in train_rows}
    val_ids = {r.match_id for r in val_rows}
    test_ids = {r.match_id for r in test_rows}

    # 1. Assert Disjoint Partitions
    tr_val_overlap = train_ids.intersection(val_ids)
    if tr_val_overlap:
        raise ValueError(f"DATA LEAKAGE VIOLATION: Overlap between Train and Validation partitions: {len(tr_val_overlap)} matches.")

    tr_te_overlap = train_ids.intersection(test_ids)
    if tr_te_overlap:
        raise ValueError(f"DATA LEAKAGE VIOLATION: Overlap between Train and Test partitions: {len(tr_te_overlap)} matches.")

    val_te_overlap = val_ids.intersection(test_ids)
    if val_te_overlap:
        raise ValueError(f"DATA LEAKAGE VIOLATION: Overlap between Validation and Test partitions: {len(val_te_overlap)} matches.")

    # 2. Assert Strict Temporal Chronology
    max_train_time = max(r.kickoff_utc for r in train_rows)

    if val_rows:
        min_val_time = min(r.kickoff_utc for r in val_rows)
        if max_train_time > min_val_time:
            raise ValueError(
                f"TEMPORAL LEAKAGE VIOLATION: Training match ({max_train_time}) occurs after Validation match ({min_val_time})."
            )
        max_val_time = max(r.kickoff_utc for r in val_rows)
    else:
        max_val_time = max_train_time

    if test_rows:
        min_test_time = min(r.kickoff_utc for r in test_rows)
        if max_val_time > min_test_time:
            raise ValueError(
                f"TEMPORAL LEAKAGE VIOLATION: Validation/Train match ({max_val_time}) occurs after Test match ({min_test_time})."
            )


class TemporalSplitter:
    """Provides deterministic, leakage-safe temporal splitting routines for Phase 4 modeling rows."""

    @staticmethod
    def _sort_rows(rows: list[ModelingRowDTO]) -> list[ModelingRowDTO]:
        """Ensures rows are sorted strictly by kickoff_utc ASC, tie-broken by match_id ASC."""
        return sorted(rows, key=lambda r: (r.kickoff_utc, str(r.match_id)))

    @classmethod
    def split_expanding_window(
        cls,
        rows: list[ModelingRowDTO],
        n_splits: int = 3,
        min_train_ratio: float = 0.50,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
    ) -> tuple[TemporalSplitManifest, list[tuple[list[ModelingRowDTO], list[ModelingRowDTO], list[ModelingRowDTO]]]]:
        """
        Creates n_splits expanding-window temporal folds where training window expands forward.
        """
        sorted_rows = cls._sort_rows(rows)
        total = len(sorted_rows)

        if total < 50:
            raise ValueError(f"Insufficient row count ({total}) for expanding window temporal split.")

        folds_data: list[tuple[list[ModelingRowDTO], list[ModelingRowDTO], list[ModelingRowDTO]]] = []
        partitions: list[TemporalSplitPartition] = []

        step_fraction = (1.0 - min_train_ratio - val_ratio - test_ratio) / max(1, n_splits - 1) if n_splits > 1 else 0.0

        for fold_idx in range(n_splits):
            current_train_ratio = min_train_ratio + fold_idx * step_fraction
            train_end_idx = int(total * current_train_ratio)
            val_end_idx = int(total * (current_train_ratio + val_ratio))
            test_end_idx = min(total, int(total * (current_train_ratio + val_ratio + test_ratio)))

            train_part = sorted_rows[:train_end_idx]
            val_part = sorted_rows[train_end_idx:val_end_idx]
            test_part = sorted_rows[val_end_idx:test_end_idx]

            validate_temporal_partition_invariants(train_part, val_part, test_part)

            partition_meta = TemporalSplitPartition(
                fold_id=fold_idx + 1,
                train_start=train_part[0].kickoff_utc.isoformat() if train_part else None,
                train_end=train_part[-1].kickoff_utc.isoformat() if train_part else None,
                train_count=len(train_part),
                val_start=val_part[0].kickoff_utc.isoformat() if val_part else None,
                val_end=val_part[-1].kickoff_utc.isoformat() if val_part else None,
                val_count=len(val_part),
                test_start=test_part[0].kickoff_utc.isoformat() if test_part else None,
                test_end=test_part[-1].kickoff_utc.isoformat() if test_part else None,
                test_count=len(test_part),
                competitions=sorted(list({str(r.competition_id) for r in sorted_rows})),
                train_match_ids=[str(r.match_id) for r in train_part],
                val_match_ids=[str(r.match_id) for r in val_part],
                test_match_ids=[str(r.match_id) for r in test_part],
            )
            partitions.append(partition_meta)
            folds_data.append((train_part, val_part, test_part))

        manifest = TemporalSplitManifest(
            strategy=TemporalSplitStrategy.EXPANDING_WINDOW,
            dataset_release_key=sorted_rows[0].dataset_release_key if sorted_rows else "mvp_a_historical:v1",
            dataset_release_fingerprint=sorted_rows[0].dataset_release_fingerprint if sorted_rows else "",
            feature_set_key=sorted_rows[0].feature_set_key if sorted_rows else "mvp_a_feature_set_v1",
            total_rows_evaluated=total,
            folds=partitions,
        )
        manifest.config_fingerprint = manifest.compute_fingerprint()

        return manifest, folds_data

    @classmethod
    def split_season_holdout(
        cls,
        rows: list[ModelingRowDTO],
        season_id_to_year: dict[UUID, str],
        train_seasons: list[str] = ["2021/2022", "2022/2023"],
        val_seasons: list[str] = [],
        test_seasons: list[str] = ["2023/2024"],
    ) -> tuple[TemporalSplitManifest, tuple[list[ModelingRowDTO], list[ModelingRowDTO], list[ModelingRowDTO]]]:
        """
        Splits dataset by explicit chronological seasons (e.g. 2021/22 + 2022/23 Train -> 2023/24 Test).
        """
        sorted_rows = cls._sort_rows(rows)

        train_part: list[ModelingRowDTO] = []
        val_part: list[ModelingRowDTO] = []
        test_part: list[ModelingRowDTO] = []

        for r in sorted_rows:
            s_year = season_id_to_year.get(r.season_id, "")
            if s_year in train_seasons:
                train_part.append(r)
            elif s_year in val_seasons:
                val_part.append(r)
            elif s_year in test_seasons:
                test_part.append(r)

        validate_temporal_partition_invariants(
            train_part, val_part, test_part,
            allow_empty_val=(len(val_seasons) == 0)
        )

        partition = TemporalSplitPartition(
            fold_id=1,
            train_start=train_part[0].kickoff_utc.isoformat() if train_part else None,
            train_end=train_part[-1].kickoff_utc.isoformat() if train_part else None,
            train_count=len(train_part),
            val_start=val_part[0].kickoff_utc.isoformat() if val_part else None,
            val_end=val_part[-1].kickoff_utc.isoformat() if val_part else None,
            val_count=len(val_part),
            test_start=test_part[0].kickoff_utc.isoformat() if test_part else None,
            test_end=test_part[-1].kickoff_utc.isoformat() if test_part else None,
            test_count=len(test_part),
            competitions=sorted(list({str(r.competition_id) for r in sorted_rows})),
            train_match_ids=[str(r.match_id) for r in train_part],
            val_match_ids=[str(r.match_id) for r in val_part],
            test_match_ids=[str(r.match_id) for r in test_part],
        )

        manifest = TemporalSplitManifest(
            strategy=TemporalSplitStrategy.SEASON_HOLDOUT,
            dataset_release_key=sorted_rows[0].dataset_release_key if sorted_rows else "mvp_a_historical:v1",
            dataset_release_fingerprint=sorted_rows[0].dataset_release_fingerprint if sorted_rows else "",
            feature_set_key=sorted_rows[0].feature_set_key if sorted_rows else "mvp_a_feature_set_v1",
            total_rows_evaluated=len(sorted_rows),
            folds=[partition],
        )
        manifest.config_fingerprint = manifest.compute_fingerprint()

        return manifest, (train_part, val_part, test_part)

    @classmethod
    def split_competition_aware(
        cls,
        rows: list[ModelingRowDTO],
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
    ) -> tuple[TemporalSplitManifest, tuple[list[ModelingRowDTO], list[ModelingRowDTO], list[ModelingRowDTO]]]:
        """
        Splits chronologically per competition to maintain exact proportional representation.
        """
        comp_groups: dict[UUID, list[ModelingRowDTO]] = {}
        for r in rows:
            comp_groups.setdefault(r.competition_id, []).append(r)

        train_all: list[ModelingRowDTO] = []
        val_all: list[ModelingRowDTO] = []
        test_all: list[ModelingRowDTO] = []

        for comp_id, c_rows in comp_groups.items():
            sorted_c = cls._sort_rows(c_rows)
            n = len(sorted_c)
            tr_end = int(n * train_ratio)
            val_end = int(n * (train_ratio + val_ratio))

            train_all.extend(sorted_c[:tr_end])
            val_all.extend(sorted_c[tr_end:val_end])
            test_all.extend(sorted_c[val_end:])

        train_sorted = cls._sort_rows(train_all)
        val_sorted = cls._sort_rows(val_all)
        test_sorted = cls._sort_rows(test_all)

        validate_temporal_partition_invariants(train_sorted, val_sorted, test_sorted)

        partition = TemporalSplitPartition(
            fold_id=1,
            train_start=train_sorted[0].kickoff_utc.isoformat() if train_sorted else None,
            train_end=train_sorted[-1].kickoff_utc.isoformat() if train_sorted else None,
            train_count=len(train_sorted),
            val_start=val_sorted[0].kickoff_utc.isoformat() if val_sorted else None,
            val_end=val_sorted[-1].kickoff_utc.isoformat() if val_sorted else None,
            val_count=len(val_sorted),
            test_start=test_sorted[0].kickoff_utc.isoformat() if test_sorted else None,
            test_end=test_sorted[-1].kickoff_utc.isoformat() if test_sorted else None,
            test_count=len(test_sorted),
            competitions=sorted(list({str(cid) for cid in comp_groups.keys()})),
            train_match_ids=[str(r.match_id) for r in train_sorted],
            val_match_ids=[str(r.match_id) for r in val_sorted],
            test_match_ids=[str(r.match_id) for r in test_sorted],
        )

        manifest = TemporalSplitManifest(
            strategy=TemporalSplitStrategy.COMPETITION_TEMPORAL,
            dataset_release_key=rows[0].dataset_release_key if rows else "mvp_a_historical:v1",
            dataset_release_fingerprint=rows[0].dataset_release_fingerprint if rows else "",
            feature_set_key=rows[0].feature_set_key if rows else "mvp_a_feature_set_v1",
            total_rows_evaluated=len(rows),
            folds=[partition],
        )
        manifest.config_fingerprint = manifest.compute_fingerprint()

        return manifest, (train_sorted, val_sorted, test_sorted)
