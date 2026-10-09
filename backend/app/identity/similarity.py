"""
Football Identity Similarity Engine
Calculates string and token set similarity metrics for candidate generation without automatic merging.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from app.identity.base import IdentityCandidateDTO
from app.identity.normalizer import IdentityNormalizer


class SimilarityEngine:
    """Diagnostic Similarity Engine for Identity Candidate Generation."""

    def __init__(self, default_review_threshold: float = 0.50) -> None:
        self.default_review_threshold = default_review_threshold

    @classmethod
    def calculate_similarity(cls, str1: str, str2: str) -> float:
        """Calculates combined string character & token set similarity score (0.0 to 1.0)."""
        norm1 = IdentityNormalizer.normalize_name(str1)
        norm2 = IdentityNormalizer.normalize_name(str2)

        if not norm1 or not norm2:
            return 0.0

        if norm1 == norm2:
            return 1.0

        # Character sequence ratio
        seq_ratio = SequenceMatcher(None, norm1, norm2).ratio()

        # Token set prefix / Jaccard matching
        tokens1 = norm1.split()
        tokens2 = norm2.split()

        matched_tokens = 0
        total_tokens = max(len(tokens1), len(tokens2))

        for t1 in tokens1:
            for t2 in tokens2:
                if t1 == t2 or (len(t1) >= 3 and len(t2) >= 3 and (t1.startswith(t2) or t2.startswith(t1))):
                    matched_tokens += 1
                    break

        token_ratio = matched_tokens / total_tokens if total_tokens > 0 else 0.0

        # Max of sequence ratio and weighted token ratio
        combined = max(seq_ratio, (0.5 * seq_ratio + 0.5 * token_ratio))
        return round(combined, 4)

    def find_candidates(
        self,
        target_name: str,
        canonical_entities: list[tuple[str, str]],  # List of (id_str, canonical_name)
        threshold: float | None = None,
    ) -> list[IdentityCandidateDTO]:
        """Generates similarity candidate DTOs for diagnostic review above threshold."""
        min_score = threshold if threshold is not None else self.default_review_threshold
        candidates: list[IdentityCandidateDTO] = []

        norm_target = IdentityNormalizer.normalize_name(target_name)

        for entity_id, canonical_name in canonical_entities:
            norm_canonical = IdentityNormalizer.normalize_name(canonical_name)
            if norm_target == norm_canonical:
                score = 1.0
            else:
                score = self.calculate_similarity(target_name, canonical_name)

            if score >= min_score:
                candidates.append(
                    IdentityCandidateDTO(
                        canonical_id=entity_id,
                        canonical_name=canonical_name,
                        similarity_score=score,
                        match_reason=f"Similarity score {score:.2f} >= threshold {min_score:.2f}",
                    )
                )

        # Sort candidates descending by score
        candidates.sort(key=lambda c: c.similarity_score, reverse=True)
        return candidates
