"""
Feature Engineering Pydantic Schemas
Validation DTOs for Feature Definitions, Feature Sets, and Feature Snapshots.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FeatureDefinitionBase(BaseModel):
    feature_key: str = Field(..., max_length=100)
    name: str = Field(..., max_length=150)
    description: str | None = Field(None, max_length=255)
    data_type: str = "FLOAT"
    category: str = "STRENGTH"
    version: str = "1.0.0"
    is_active: bool = True

class FeatureDefinitionResponse(FeatureDefinitionBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FeatureSetBase(BaseModel):
    name: str = Field(..., max_length=100)
    version: str = Field(..., max_length=20)
    description: str | None = Field(None, max_length=255)
    is_active: bool = True

class FeatureSetResponse(FeatureSetBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FeatureSnapshotBase(BaseModel):
    snapshot_type: str = "FINAL"
    feature_version: str = "1.0.0"
    cutoff_timestamp: datetime
    feature_values: dict[str, Any]
    missing_features: dict[str, Any] | None = None
    data_quality_metadata: dict[str, Any] | None = None

class FeatureSnapshotCreate(FeatureSnapshotBase):
    match_id: UUID
    feature_set_id: UUID

class FeatureSnapshotResponse(FeatureSnapshotBase):
    id: UUID
    match_id: UUID
    feature_set_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
