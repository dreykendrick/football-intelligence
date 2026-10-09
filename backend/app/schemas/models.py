"""
Model Registry Pydantic Schemas
Validation DTOs for Logical Models, Model Versions, and Lifecycle Statuses.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelBase(BaseModel):
    model_key: str = Field(..., max_length=50)
    name: str = Field(..., max_length=100)
    model_family: str = "POISSON"
    description: str | None = Field(None, max_length=255)

class ModelResponse(ModelBase):
    id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ModelVersionBase(BaseModel):
    version: str = Field(..., max_length=30)
    lifecycle_status: str = "EXPERIMENTAL"
    training_start_date: datetime | None = None
    training_end_date: datetime | None = None
    hyperparameters: dict[str, Any] | None = None
    artifact_path: str | None = Field(None, max_length=255)
    code_version: str | None = Field(None, max_length=50)
    notes: str | None = Field(None, max_length=255)

class ModelVersionCreate(ModelVersionBase):
    model_id: UUID
    feature_set_id: UUID

class ModelVersionResponse(ModelVersionBase):
    id: UUID
    model_id: UUID
    feature_set_id: UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
