"""
Phase 4 Evaluation Metrics Engine & Scientific Report Architecture
Implements multiclass Log Loss, Brier Score, Ranked Probability Score (RPS), Expected Calibration Error (ECE),
reliability binning, confusion matrices, and structured serializable evaluation reports.
"""
from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.base import IPredictionModel
from app.models.dataset_dto import ModelingRowDTO
from app.models.splitting import TemporalSplitManifest
from app.models.targets import AWAY_WIN_LABEL, CANONICAL_1X2_OUTCOMES, DRAW_LABEL, HOME_WIN_LABEL, INT_TO_1X2_MAP


def multiclass_log_loss(y_true: list[int], y_probs: list[list[float]], eps: float = 1e-15) -> float:
    """
    Computes standard multiclass cross-entropy loss with epsilon clipping.
    y_true: list of integer class labels (0=HOME_WIN, 1=DRAW, 2=AWAY_WIN).
    y_probs: list of 3-element probability vectors [p0, p1, p2].
    """
    if not y_true or not y_probs:
        raise ValueError("Cannot calculate log loss on empty inputs.")
    if len(y_true) != len(y_probs):
        raise ValueError(f"Length mismatch: {len(y_true)} true labels vs {len(y_probs)} probability vectors.")

    total_loss = 0.0
    n = len(y_true)

    for y, p_vec in zip(y_true, y_probs):
        if len(p_vec) != 3:
            raise ValueError(f"Expected 3-class probability vector, got length {len(p_vec)}.")
        # Clip to avoid log(0)
        clipped = [max(eps, min(1.0 - eps, float(p))) for p in p_vec]
        # Re-normalize
        s = sum(clipped)
        norm_p = [p / s for p in clipped]

        if y not in (HOME_WIN_LABEL, DRAW_LABEL, AWAY_WIN_LABEL):
            raise ValueError(f"Invalid outcome class label: {y}")

        loss = -math.log(norm_p[y])
        total_loss += loss

    return round(total_loss / n, 6)


def multiclass_brier_score(y_true: list[int], y_probs: list[list[float]]) -> float:
    """
    Computes standard multiclass Brier score: (1/N) * sum_i sum_k (p_{ik} - y_{ik})^2.
    Bounded in [0, 2] for 3-class problems. Lower is better.
    """
    if not y_true or not y_probs:
        raise ValueError("Cannot calculate Brier score on empty inputs.")
    if len(y_true) != len(y_probs):
        raise ValueError(f"Length mismatch: {len(y_true)} true labels vs {len(y_probs)} probability vectors.")

    total_brier = 0.0
    n = len(y_true)

    for y, p_vec in zip(y_true, y_probs):
        if len(p_vec) != 3:
            raise ValueError(f"Expected 3-class probability vector, got length {len(p_vec)}.")
        # One-hot target vector
        target_vec = [1.0 if k == y else 0.0 for k in range(3)]
        row_sq_err = sum((float(p) - t) ** 2 for p, t in zip(p_vec, target_vec))
        total_brier += row_sq_err

    return round(total_brier / n, 6)


def ranked_probability_score(y_true: list[int], y_probs: list[list[float]]) -> float:
    """
    Computes Ranked Probability Score (RPS) for ordered 1X2 outcomes: (Home Win < Draw < Away Win).
    RPS = (1 / (K-1)) * sum_{k=0}^{K-2} (CDF_pred(k) - CDF_actual(k))^2 where K=3.
    """
    if not y_true or not y_probs:
        raise ValueError("Cannot calculate RPS on empty inputs.")
    if len(y_true) != len(y_probs):
        raise ValueError(f"Length mismatch: {len(y_true)} true labels vs {len(y_probs)} probability vectors.")

    total_rps = 0.0
    n = len(y_true)

    for y, p_vec in zip(y_true, y_probs):
        if len(p_vec) != 3:
            raise ValueError(f"Expected 3-class probability vector, got length {len(p_vec)}.")

        # Cumulative probability distribution
        p0, p1, p2 = float(p_vec[0]), float(p_vec[1]), float(p_vec[2])
        cdf_p0 = p0
        cdf_p1 = p0 + p1

        # Cumulative actual distribution
        act_p0 = 1.0 if y == 0 else 0.0
        act_p1 = 1.0 if y in (0, 1) else 0.0

        # K=3 -> K-1=2 steps
        rps_i = 0.5 * ((cdf_p0 - act_p0) ** 2 + (cdf_p1 - act_p1) ** 2)
        total_rps += rps_i

    return round(total_rps / n, 6)


def per_class_brier_scores(y_true: list[int], y_probs: list[list[float]]) -> dict[str, float]:
    """Computes binary Brier score components for Home Win, Draw, and Away Win separately."""
    n = len(y_true)
    if n == 0:
        return {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}

    h_err = sum((float(p[0]) - (1.0 if y == 0 else 0.0)) ** 2 for y, p in zip(y_true, y_probs)) / n
    d_err = sum((float(p[1]) - (1.0 if y == 1 else 0.0)) ** 2 for y, p in zip(y_true, y_probs)) / n
    a_err = sum((float(p[2]) - (1.0 if y == 2 else 0.0)) ** 2 for y, p in zip(y_true, y_probs)) / n

    return {
        "home_win": round(h_err, 6),
        "draw": round(d_err, 6),
        "away_win": round(a_err, 6),
    }


def accuracy_score(y_true: list[int], y_pred: list[int]) -> float:
    """Computes overall multiclass classification accuracy."""
    if not y_true:
        return 0.0
    correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
    return round(correct / len(y_true), 6)


def balanced_accuracy_score(y_true: list[int], y_pred: list[int]) -> float:
    """Computes macro-averaged recall across all 3 classes."""
    recalls: list[float] = []
    for cls_idx in (HOME_WIN_LABEL, DRAW_LABEL, AWAY_WIN_LABEL):
        total_cls = sum(1 for yt in y_true if yt == cls_idx)
        if total_cls > 0:
            correct_cls = sum(1 for yt, yp in zip(y_true, y_pred) if yt == cls_idx and yp == cls_idx)
            recalls.append(correct_cls / total_cls)
    if not recalls:
        return 0.0
    return round(sum(recalls) / len(recalls), 6)


def confusion_matrix_3x3(y_true: list[int], y_pred: list[int]) -> list[list[int]]:
    """Generates 3x3 confusion matrix where matrix[actual][predicted] = count."""
    matrix = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    for yt, yp in zip(y_true, y_pred):
        if 0 <= yt <= 2 and 0 <= yp <= 2:
            matrix[yt][yp] += 1
    return matrix


def prediction_entropy(y_probs: list[list[float]], eps: float = 1e-15) -> float:
    """Computes mean Shannon entropy of predicted probability distributions in nats."""
    if not y_probs:
        return 0.0
    total_ent = 0.0
    for p_vec in y_probs:
        ent = -sum(float(p) * math.log(max(eps, float(p))) for p in p_vec if float(p) > 0)
        total_ent += ent
    return round(total_ent / len(y_probs), 6)


def reliability_diagram_bins(
    y_true: list[int], y_probs: list[list[float]], n_bins: int = 10
) -> list[dict[str, Any]]:
    """
    Groups predictions by confidence of the top predicted outcome into n_bins equal intervals.
    Returns list of dicts with bin metadata: confidence, empirical accuracy, sample count.
    """
    bins_data: list[dict[str, Any]] = []
    bin_width = 1.0 / n_bins

    for b in range(n_bins):
        low = b * bin_width
        high = (b + 1) * bin_width
        bin_preds: list[int] = []
        bin_trues: list[int] = []
        bin_confs: list[float] = []

        for yt, p_vec in zip(y_true, y_probs):
            max_p = max(p_vec)
            pred_cls = p_vec.index(max_p)
            # Include upper boundary in last bin
            if (low <= max_p < high) or (b == n_bins - 1 and max_p == 1.0):
                bin_preds.append(pred_cls)
                bin_trues.append(yt)
                bin_confs.append(float(max_p))

        count = len(bin_confs)
        if count > 0:
            avg_conf = sum(bin_confs) / count
            acc = sum(1 for yt, yp in zip(bin_trues, bin_preds) if yt == yp) / count
        else:
            avg_conf = (low + high) / 2.0
            acc = 0.0

        bins_data.append({
            "bin_index": b,
            "bin_lower": round(low, 4),
            "bin_upper": round(high, 4),
            "sample_count": count,
            "avg_confidence": round(avg_conf, 6),
            "empirical_accuracy": round(acc, 6),
        })

    return bins_data


def expected_calibration_error(
    y_true: list[int], y_probs: list[list[float]], n_bins: int = 10
) -> float:
    """Computes sample-weighted Expected Calibration Error (ECE)."""
    bins = reliability_diagram_bins(y_true, y_probs, n_bins=n_bins)
    total_samples = len(y_true)
    if total_samples == 0:
        return 0.0

    ece = 0.0
    for b in bins:
        count = b["sample_count"]
        if count > 0:
            diff = abs(b["empirical_accuracy"] - b["avg_confidence"])
            ece += (count / total_samples) * diff

    return round(ece, 6)


class MetricSummaryDTO(BaseModel):
    """Container for computed evaluation metrics on a dataset partition."""

    sample_size: int = 0
    log_loss: float = 0.0
    brier_score: float = 0.0
    ranked_probability_score: float = 0.0
    brier_home: float = 0.0
    brier_draw: float = 0.0
    brier_away: float = 0.0
    accuracy: float = 0.0
    balanced_accuracy: float = 0.0
    expected_calibration_error: float = 0.0
    mean_prediction_entropy: float = 0.0
    actual_distribution: dict[str, float] = Field(default_factory=dict)
    predicted_distribution: dict[str, float] = Field(default_factory=dict)
    confusion_matrix: list[list[int]] = Field(default_factory=list)


class FoldEvaluationResultDTO(BaseModel):
    """Evaluation result for a single cross-validation or temporal split fold."""

    fold_id: int
    train_count: int
    test_count: int
    metrics: MetricSummaryDTO


class EvaluationReportDTO(BaseModel):
    """Structured, reproducible Phase 4 model evaluation report."""

    report_id: str
    model_key: str
    model_family: str
    model_version: str
    model_artifact_fingerprint: str
    dataset_release_key: str
    dataset_release_fingerprint: str
    feature_set_key: str
    split_strategy: str
    split_manifest_id: str | None = None
    created_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    overall_metrics: MetricSummaryDTO
    fold_results: list[FoldEvaluationResultDTO] = Field(default_factory=list)
    competition_breakdowns: dict[str, MetricSummaryDTO] = Field(default_factory=dict)
    season_breakdowns: dict[str, MetricSummaryDTO] = Field(default_factory=dict)
    calibration_bins: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ModelEvaluator:
    """Scientific evaluation engine executing metric computation and reporting."""

    @classmethod
    def compute_metric_summary(
        cls, y_true: list[int], y_probs: list[list[float]]
    ) -> MetricSummaryDTO:
        """Computes all primary, secondary, and diagnostic metrics for given ground truth and probabilities."""
        n = len(y_true)
        if n == 0:
            return MetricSummaryDTO()

        ll = multiclass_log_loss(y_true, y_probs)
        bs = multiclass_brier_score(y_true, y_probs)
        rps = ranked_probability_score(y_true, y_probs)
        per_brier = per_class_brier_scores(y_true, y_probs)

        # Predictions (argmax)
        y_pred = [p_vec.index(max(p_vec)) for p_vec in y_probs]

        acc = accuracy_score(y_true, y_pred)
        b_acc = balanced_accuracy_score(y_true, y_pred)
        cm = confusion_matrix_3x3(y_true, y_pred)
        ece = expected_calibration_error(y_true, y_probs)
        ent = prediction_entropy(y_probs)

        # Actual distribution
        act_counts = {0: 0, 1: 0, 2: 0}
        for yt in y_true:
            act_counts[yt] = act_counts.get(yt, 0) + 1
        act_dist = {INT_TO_1X2_MAP[k]: round(act_counts[k] / n, 4) for k in (0, 1, 2)}

        # Predicted distribution
        pred_counts = {0: 0, 1: 0, 2: 0}
        for yp in y_pred:
            pred_counts[yp] = pred_counts.get(yp, 0) + 1
        pred_dist = {INT_TO_1X2_MAP[k]: round(pred_counts[k] / n, 4) for k in (0, 1, 2)}

        return MetricSummaryDTO(
            sample_size=n,
            log_loss=ll,
            brier_score=bs,
            ranked_probability_score=rps,
            brier_home=per_brier["home_win"],
            brier_draw=per_brier["draw"],
            brier_away=per_brier["away_win"],
            accuracy=acc,
            balanced_accuracy=b_acc,
            expected_calibration_error=ece,
            mean_prediction_entropy=ent,
            actual_distribution=act_dist,
            predicted_distribution=pred_dist,
            confusion_matrix=cm,
        )

    @classmethod
    def evaluate_model(
        cls,
        model: IPredictionModel,
        test_rows: list[ModelingRowDTO],
        split_manifest: TemporalSplitManifest | None = None,
        report_id: str | None = None,
    ) -> EvaluationReportDTO:
        """
        Evaluates a fitted prediction model against unseen test rows.
        Generates overall metrics, competition breakdowns, calibration curves, and warnings.
        """
        if not test_rows:
            raise ValueError("Cannot evaluate model on empty test rows.")

        y_true: list[int] = []
        y_probs: list[list[float]] = []

        comp_rows: dict[str, list[tuple[int, list[float]]]] = {}
        season_rows: dict[str, list[tuple[int, list[float]]]] = {}

        for r in test_rows:
            t_val = r.targets.get("match_result_1x2_v1")
            if t_val is None:
                continue
            yt = int(t_val)
            p_vec = model.predict_proba_vector(r)

            y_true.append(yt)
            y_probs.append(p_vec)

            cid = str(r.competition_id)
            comp_rows.setdefault(cid, []).append((yt, p_vec))

            sid = str(r.season_id)
            season_rows.setdefault(sid, []).append((yt, p_vec))

        overall = cls.compute_metric_summary(y_true, y_probs)
        cal_bins = reliability_diagram_bins(y_true, y_probs)

        # Competition breakdowns
        comp_breakdowns: dict[str, MetricSummaryDTO] = {}
        for cid, pairs in comp_rows.items():
            c_yt = [p[0] for p in pairs]
            c_yp = [p[1] for p in pairs]
            comp_breakdowns[cid] = cls.compute_metric_summary(c_yt, c_yp)

        # Warnings
        warnings: list[str] = []
        if overall.sample_size < 100:
            warnings.append(f"Small evaluation sample size ({overall.sample_size} matches). Metrics may exhibit high variance.")
        if overall.expected_calibration_error > 0.15:
            warnings.append(f"High Expected Calibration Error ({overall.expected_calibration_error:.4f}). Probabilities appear uncalibrated.")
        if overall.predicted_distribution.get("DRAW", 0.0) == 0.0:
            warnings.append("Model never predicts DRAW as the top outcome class (typical for uncalibrated baselines).")

        meta = model.metadata()
        art_fp = getattr(model, "artifact", None)
        fp_str = art_fp.artifact_fingerprint if art_fp else "unfitted_in_memory"

        return EvaluationReportDTO(
            report_id=report_id or f"eval_{model.model_key}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            model_key=model.model_key,
            model_family=model.model_family,
            model_version=model.version,
            model_artifact_fingerprint=fp_str,
            dataset_release_key=test_rows[0].dataset_release_key,
            dataset_release_fingerprint=test_rows[0].dataset_release_fingerprint,
            feature_set_key=test_rows[0].feature_set_key,
            split_strategy=split_manifest.strategy.value if split_manifest else "TEST_HOLDOUT",
            split_manifest_id=split_manifest.manifest_id if split_manifest else None,
            overall_metrics=overall,
            competition_breakdowns=comp_breakdowns,
            calibration_bins=cal_bins,
            warnings=warnings,
        )
