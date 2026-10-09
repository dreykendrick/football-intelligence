"""
Identity String Normalizer
Applies Unicode normalization, case folding, and whitespace collapsing while preserving identity-significant tokens.
"""
from __future__ import annotations

import re
import unicodedata


class IdentityNormalizer:
    """Safe String Normalization Engine for Football Entities."""

    # Identity-significant tokens that MUST NEVER be stripped or collapsed
    PRESERVED_TOKENS: set[str] = {
        "fc", "united", "city", "town", "rovers", "wanderers", "athletic",
        "real", "sporting", "inter", "milan", "ac", "afc", "sc", "sv", "vfb",
        "borussia", "bayern", "bayer", "dynamo", "lokomotiv", "red", "star",
        "club", "deportivo", "racing", "standard", "olympique", "union",
    }

    @classmethod
    def normalize_name(cls, raw_name: str | None) -> str:
        """Transforms raw entity string to a safe, normalized representation for matching."""
        if not raw_name:
            return ""

        # 1. Unicode NFKD normalization (decomposes accents, e.g. Atletico -> Atletico)
        nfkd = unicodedata.normalize("NFKD", raw_name)
        ascii_text = nfkd.encode("ASCII", "ignore").decode("utf-8")

        # 2. Case folding & trimming
        text = ascii_text.lower().strip()

        # 3. Replace common abbreviations with canonical forms (e.g. St. -> Saint, & -> and)
        text = re.sub(r"\bst\b\.?", "saint", text)
        text = re.sub(r"&", "and", text)

        # 4. Remove punctuation except spaces
        text = re.sub(r"[^\w\s]", "", text)

        # 5. Collapse multiple spaces
        text = re.sub(r"\s+", " ", text).strip()

        return text
