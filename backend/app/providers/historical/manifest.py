"""
Historical Data Manifest Loader
Loads and validates declarative target coverage specifications for historical dataset acquisition.
"""
from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from app.providers.historical.base import SourceSpecification
from app.providers.historical.football_data_uk import FootballDataUKProvider


class ManifestSourceItem(BaseModel):
    competition_code: str
    season_year: str
    is_required: bool = True


class HistoricalManifestSchema(BaseModel):
    provider_key: str = "football_data_uk"
    description: str = ""
    version: str = "1.0.0"
    sources: list[ManifestSourceItem] = Field(default_factory=list)


# Fallback dictionary manifest if PyYAML is unavailable
DEFAULT_MANIFEST_DATA: dict[str, Any] = {
    "provider_key": "football_data_uk",
    "description": "MVP-A Required Historical Data Sources (4 Competitions x 3 Completed Seasons = 12 Datasets)",
    "version": "1.0.0",
    "sources": [
        {"competition_code": "EPL", "season_year": "2021-22", "is_required": True},
        {"competition_code": "EPL", "season_year": "2022-23", "is_required": True},
        {"competition_code": "EPL", "season_year": "2023-24", "is_required": True},
        {"competition_code": "LA_LIGA", "season_year": "2021-22", "is_required": True},
        {"competition_code": "LA_LIGA", "season_year": "2022-23", "is_required": True},
        {"competition_code": "LA_LIGA", "season_year": "2023-24", "is_required": True},
        {"competition_code": "SERIE_A", "season_year": "2021-22", "is_required": True},
        {"competition_code": "SERIE_A", "season_year": "2022-23", "is_required": True},
        {"competition_code": "SERIE_A", "season_year": "2023-24", "is_required": True},
        {"competition_code": "BUNDESLIGA", "season_year": "2021-22", "is_required": True},
        {"competition_code": "BUNDESLIGA", "season_year": "2022-23", "is_required": True},
        {"competition_code": "BUNDESLIGA", "season_year": "2023-24", "is_required": True},
    ],
}


class HistoricalManifestLoader:
    """Loads declared target historical sources into validated SourceSpecification instances."""

    @classmethod
    def load_manifest(cls, manifest_path: str | None = None) -> list[SourceSpecification]:
        provider = FootballDataUKProvider()
        raw_data = DEFAULT_MANIFEST_DATA

        if manifest_path and os.path.exists(manifest_path):
            try:
                import yaml  # type: ignore

                with open(manifest_path, encoding="utf-8") as f:
                    raw_data = yaml.safe_load(f)
            except ImportError:
                pass

        schema = HistoricalManifestSchema.model_validate(raw_data)
        specs: list[SourceSpecification] = []

        for item in schema.sources:
            provider_comp = provider.format_competition_code(item.competition_code)
            provider_season = provider.format_season_code(item.season_year)
            url = provider.resolve_source_url(item.competition_code, item.season_year)

            specs.append(
                SourceSpecification(
                    provider_key=schema.provider_key,
                    competition_code=item.competition_code,
                    season_year=item.season_year,
                    provider_competition_code=provider_comp,
                    provider_season_code=provider_season,
                    source_url=url,
                    is_required=item.is_required,
                )
            )

        return specs


class HistoricalSourceCatalog:
    """Catalog interface providing lookup of declared raw source specifications."""

    @classmethod
    def load_default_manifest(cls) -> HistoricalSourceCatalog:
        specs = HistoricalManifestLoader.load_manifest()
        return cls(specs)

    def __init__(self, specs: list[SourceSpecification]) -> None:
        self.specs = specs
        self._map: dict[tuple[str, str], SourceSpecification] = {}
        for s in specs:
            comp_codes = {s.competition_code, s.provider_competition_code}
            if s.competition_code == "EPL":
                comp_codes.add("E0")
            elif s.competition_code == "LA_LIGA":
                comp_codes.add("SP1")
            elif s.competition_code == "SERIE_A":
                comp_codes.add("I1")
            elif s.competition_code == "BUNDESLIGA":
                comp_codes.add("D1")

            season_variants = {s.season_year, s.season_year.replace("-", "/")}
            if "-" in s.season_year:
                parts = s.season_year.split("-")
                if len(parts) == 2:
                    y1, y2 = parts[0], parts[1]
                    if len(y1) == 4 and len(y2) == 2:
                        full_variant = f"{y1}/20{y2}"
                        season_variants.add(full_variant)
                        season_variants.add(f"{y1}-20{y2}")

            for cc in comp_codes:
                for sv in season_variants:
                    self._map[(cc, sv)] = s

    def get_source_spec(self, competition_code: str, season_year: str) -> SourceSpecification | None:
        return self._map.get((competition_code, season_year))
