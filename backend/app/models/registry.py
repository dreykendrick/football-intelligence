"""
Central Model Registry Architecture
Provides registration, lookup, and metadata discovery for all Phase 4 statistical prediction models.
"""
from __future__ import annotations

from typing import Any, Type

from app.models.base import IPredictionModel


class ModelRegistry:
    """Central registry catalog of available statistical prediction models."""

    def __init__(self) -> None:
        self._registry: dict[str, Type[IPredictionModel]] = {}

    def register(self, model_cls: Type[IPredictionModel]) -> None:
        """Registers a model class under its model_key attribute."""
        key = getattr(model_cls, "model_key", None)
        if not key:
            raise ValueError(f"Model class {model_cls.__name__} must define a non-empty 'model_key' attribute.")
        self._registry[key] = model_cls

    def get_model_class(self, model_key: str) -> Type[IPredictionModel]:
        """Retrieves a registered model class by model_key."""
        if model_key not in self._registry:
            raise KeyError(f"Model key '{model_key}' is not registered in ModelRegistry.")
        return self._registry[model_key]

    def create_model_instance(self, model_key: str, **kwargs: Any) -> IPredictionModel:
        """Instantiates a registered prediction model by model_key."""
        cls = self.get_model_class(model_key)
        return cls(**kwargs)

    def list_models(self) -> list[dict[str, Any]]:
        """Returns metadata descriptors for all registered models."""
        res: list[dict[str, Any]] = []
        for key in sorted(self._registry.keys()):
            cls = self._registry[key]
            instance = cls()
            res.append(instance.metadata())
        return res


global_model_registry = ModelRegistry()
