"""
Unit Tests for Football Identity Normalizer
Verifies Unicode NFKD decomposition, case folding, and preservation of identity-significant tokens.
"""
import pytest

from app.identity.normalizer import IdentityNormalizer


@pytest.mark.unit
def test_unicode_and_case_normalization():
    assert IdentityNormalizer.normalize_name("  Atlético Madrid ") == "atletico madrid"
    assert IdentityNormalizer.normalize_name("ARSENAL") == "arsenal"


@pytest.mark.unit
def test_abbreviation_and_punctuation_normalization():
    assert IdentityNormalizer.normalize_name("St. Mirren") == "saint mirren"
    assert IdentityNormalizer.normalize_name("Brighton & Hove Albion") == "brighton and hove albion"


@pytest.mark.unit
def test_preserves_identity_significant_tokens():
    # Identity-significant tokens like FC, United, City must be preserved
    norm_utd = IdentityNormalizer.normalize_name("Manchester United")
    norm_city = IdentityNormalizer.normalize_name("Manchester City")

    assert "united" in norm_utd
    assert "city" in norm_city
    assert norm_utd != norm_city
