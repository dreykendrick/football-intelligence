# Modeling Architecture, Preprocessing & Serialization

## Overview

The model architecture in Phase 4 provides a standardized, type-safe interface (`IPredictionModel`), an isolated training-only feature preprocessor (`ModelPreprocessor`), a global model registry (`ModelRegistry`), and deterministic artifact serialization (`TrainedModelArtifact`).

---

## 1. Abstract Model Interface (`IPredictionModel`)

All Phase 4 prediction models inherit from `IPredictionModel` (`app/models/base.py`) and implement the following contract:

```python
class IPredictionModel(ABC):
    model_key: str
    model_family: str
    version: str
    target_key: str
    feature_set_key: str
    lifecycle_status: str

    @abstractmethod
    def fit(self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None) -> TrainedModelArtifact:
        """Fits model parameters using training rows only."""

    @abstractmethod
    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        """Generates raw uncalibrated predictions for a single row."""

    @abstractmethod
    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        """Returns target outcomes mapped to probabilities."""

    @abstractmethod
    def save_artifact(self, filepath: str) -> None:
        """Persists trained model artifact JSON to disk."""

    @abstractmethod
    def load_artifact(self, filepath: str) -> None:
        """Restores model state from trained artifact JSON."""
```

---

## 2. Preprocessor & Training-Only Isolation (`ModelPreprocessor`)

The `ModelPreprocessor` handles feature transformations with strict temporal isolation:

1. **Training-Only Fitting:** Imputation medians and scaling parameters ($\mu$, $\sigma$) are computed **strictly from training set rows** during `fit()`.
2. **Missing Indicators:** Adds missingness indicators (`{fkey}__is_missing`) for numerical features with missing values in training.
3. **Median Imputation:** Replaces missing values with training medians (or `0.0` default).
4. **Standardization:** Applies Z-score normalization (`(x - mean) / std`) where $\sigma > 10^{-6}$.
5. **Zero-Variance Audit:** Detects and flags structural zero-variance features in the `PreprocessingArtifact`.

During prediction/inference, `transform_row(row)` applies the pre-computed `PreprocessingArtifact` parameters without modifying fitted medians or scaling statistics.

---

## 3. Central Model Registry (`ModelRegistry`)

The central model registry tracks all registered model classes and trained instances:

- `global_model_registry.register(model_class)`: Registers a model implementation class.
- `global_model_registry.get_model_class(model_key)`: Looks up model constructor by key.
- `global_model_registry.list_models()`: Enumerates registered model metadata, target key, family, and lifecycle status.

---

## 4. Artifact Serialization (`TrainedModelArtifact`)

Trained model artifacts are fully self-contained JSON objects:

```json
{
  "model_key": "multinomial_logistic_1x2_v1",
  "model_family": "MULTINOMIAL_LOGISTIC",
  "version": "1.0.0",
  "target_key": "match_result_1x2_v1",
  "feature_set_key": "mvp_a_feature_set_v1",
  "lifecycle_status": "EXPERIMENTAL",
  "training_window": {
    "row_count": 1000,
    "modeling_dataset_key": "mvp_a_modeling_dataset_v1",
    "modeling_dataset_fingerprint": "a3f5..."
  },
  "preprocessor_artifact": { ... },
  "hyperparameters": { "C": 1.0, "max_iter": 500 },
  "weights_payload": { ... },
  "created_at": "2026-09-08T00:00:00Z",
  "artifact_fingerprint": "e7b1..."
}
```

The `artifact_fingerprint` is computed via SHA-256 over key fields to ensure tamper evidence and reproducibility.
