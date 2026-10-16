"""
SQLAlchemy ORM Models Package Export
Exposes declarative Base and all domain entities.
"""
from app.db.base import Base, BaseMixin
from app.db.models.core import (
    Competition,
    Match,
    MatchStatistic,
    Season,
    SystemAuditLog,
    Team,
    TeamAliasMapping,
)
from app.db.models.dataset import (
    HistoricalDatasetExclusion,
    HistoricalDatasetMatch,
    HistoricalDatasetRelease,
    HistoricalDatasetSeason,
)
from app.db.models.evaluation import (
    BacktestRun,
    DataQualityLog,
    EvaluationMetric,
    EvaluationRun,
)
from app.db.models.features import (
    FeatureDefinition,
    FeatureSet,
    FeatureSetFeature,
    FeatureSnapshot,
)
from app.db.models.mappings import (
    IngestionBatch,
    Provider,
    ProviderCompetitionMapping,
    ProviderMatchMapping,
    ProviderSeasonMapping,
    ProviderTeamMapping,
    RawSourceRecord,
)
from app.db.models.models import (
    Model,
    ModelLifecycleHistory,
    ModelVersion,
)
from app.db.models.predictions import (
    PredictionSnapshot,
)
from app.db.models.shadow import (
    MonitoringAlert,
    ShadowEvaluation,
    ShadowPrediction,
    ShadowPredictionRun,
)

__all__ = [
    "Base",
    "BaseMixin",
    "SystemAuditLog",
    "Competition",
    "Season",
    "Team",
    "TeamAliasMapping",
    "Match",
    "MatchStatistic",
    "Provider",
    "IngestionBatch",
    "ProviderCompetitionMapping",
    "ProviderSeasonMapping",
    "ProviderTeamMapping",
    "ProviderMatchMapping",
    "RawSourceRecord",
    "FeatureDefinition",
    "FeatureSet",
    "FeatureSetFeature",
    "FeatureSnapshot",
    "Model",
    "ModelVersion",
    "ModelLifecycleHistory",
    "PredictionSnapshot",
    "BacktestRun",
    "EvaluationRun",
    "EvaluationMetric",
    "DataQualityLog",
    "HistoricalDatasetRelease",
    "HistoricalDatasetSeason",
    "HistoricalDatasetMatch",
    "HistoricalDatasetExclusion",
    "ShadowPredictionRun",
    "ShadowPrediction",
    "ShadowEvaluation",
    "MonitoringAlert",
]
