"""
Unit Tests for Football Identity Similarity Engine
Verifies similarity score calculations and candidate generation.
"""
from uuid import uuid4

import pytest

from app.identity.similarity import SimilarityEngine


@pytest.mark.unit
def test_exact_match_similarity_is_one():
    score = SimilarityEngine.calculate_similarity("Manchester United", "Manchester United")
    assert score == 1.0


@pytest.mark.unit
def test_similar_names_candidate_score():
    score = SimilarityEngine.calculate_similarity("Manchester United", "Man United")
    assert score >= 0.70


@pytest.mark.unit
def test_candidate_generation():
    engine = SimilarityEngine(default_review_threshold=0.50)
    id1 = uuid4()
    id2 = uuid4()
    id3 = uuid4()

    canonical_list = [
        (id1, "Manchester United"),
        (id2, "Manchester City"),
        (id3, "Arsenal"),
    ]

    candidates = engine.find_candidates("Man United", canonical_list)
    assert len(candidates) >= 1
    assert candidates[0].canonical_name == "Manchester United"
    assert candidates[0].similarity_score >= 0.70
