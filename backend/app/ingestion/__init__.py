"""
Ingestion Package Export
Exposes provider protocols, raw match DTOs, provider adapters, and domain normalizers.
"""
from app.ingestion.base import (
    HistoricalFootballProvider,
    HistoricalProviderBatchResultDTO,
    IngestionStatusEnum,
    RawMatchRowDTO,
)
from app.ingestion.historical.football_data_uk import FootballDataUKProvider

__all__ = [
    "HistoricalFootballProvider",
    "RawMatchRowDTO",
    "HistoricalProviderBatchResultDTO",
    "IngestionStatusEnum",
    "FootballDataUKProvider",
]
