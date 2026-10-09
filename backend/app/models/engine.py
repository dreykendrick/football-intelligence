"""
Goal Distribution Engine & Probability Invariant Validator Architecture
Provides mathematical mechanisms to derive exact score matrices, 1X2, BTTS, and Over/Under 2.5
probabilities from expected goals (lambda) parameters under independent Poisson distribution.
"""
from __future__ import annotations

import math
from typing import Any
import numpy as np
from scipy.stats import poisson
from pydantic import BaseModel, Field

from app.models.base import BTTSProbabilityDTO, OneXTwoProbabilityDTO, OverUnderProbabilityDTO

PROBABILITY_SUM_TOLERANCE: float = 1e-6


class ScoreProbabilityMatrix(BaseModel):
    """Container for joint score probability grid and mass accounting."""

    max_home_goals: int = 10
    max_away_goals: int = 10
    grid_size: int = 11
    matrix: list[list[float]] = Field(default_factory=list)
    retained_probability_mass: float = 1.0
    tail_probability_mass: float = 0.0
    normalized: bool = True
    distribution_family: str = "INDEPENDENT_POISSON"
    assumptions: list[str] = Field(
        default_factory=lambda: ["HomeGoals ⟂ AwayGoals | pre-match features"]
    )


class ProbabilityInvariantValidator:
    """Validator ensuring derived probabilities satisfy mathematical axioms."""

    @staticmethod
    def validate_lambda(lambda_val: float, name: str = "lambda") -> None:
        if not math.isfinite(lambda_val) or lambda_val <= 0.0:
            raise ValueError(f"Invalid {name}: must be finite and strictly positive (> 0), got: {lambda_val}")

    @staticmethod
    def validate_probability_bounds(prob: float, name: str = "probability") -> None:
        if not math.isfinite(prob) or prob < -PROBABILITY_SUM_TOLERANCE or prob > 1.0 + PROBABILITY_SUM_TOLERANCE:
            raise ValueError(f"Probability out of bounds [0, 1] for {name}: got {prob}")

    @staticmethod
    def validate_sum_to_one(prob_sum: float, name: str = "probability_sum") -> None:
        if abs(prob_sum - 1.0) > PROBABILITY_SUM_TOLERANCE:
            raise ValueError(f"Probability sum for {name} does not sum to 1.0 within tolerance: got {prob_sum}")

    @staticmethod
    def validate_goal_prediction_consistency(prediction: Any, tolerance: float = 1e-4) -> None:
        """
        Validates mathematical consistency of a MatchProbabilityPrediction:
        1. Bounds: [0, 1] for all probabilities and sum to 1.0.
        2. Exact reconstructability from lambda pair (if present).
        """
        ph = prediction.one_x_two.home_win
        pd = prediction.one_x_two.draw
        pa = prediction.one_x_two.away_win

        ProbabilityInvariantValidator.validate_probability_bounds(ph, "home_win")
        ProbabilityInvariantValidator.validate_probability_bounds(pd, "draw")
        ProbabilityInvariantValidator.validate_probability_bounds(pa, "away_win")
        ProbabilityInvariantValidator.validate_sum_to_one(ph + pd + pa, "1X2 sum")

        if prediction.btts is not None:
            ProbabilityInvariantValidator.validate_probability_bounds(prediction.btts.yes, "btts_yes")
            ProbabilityInvariantValidator.validate_probability_bounds(prediction.btts.no, "btts_no")
            ProbabilityInvariantValidator.validate_sum_to_one(prediction.btts.yes + prediction.btts.no, "BTTS sum")

        if prediction.over_under_2_5 is not None:
            ProbabilityInvariantValidator.validate_probability_bounds(prediction.over_under_2_5.over, "over_2_5")
            ProbabilityInvariantValidator.validate_probability_bounds(prediction.over_under_2_5.under, "under_2_5")
            ProbabilityInvariantValidator.validate_sum_to_one(
                prediction.over_under_2_5.over + prediction.over_under_2_5.under, "O/U 2.5 sum"
            )

        if prediction.lambda_home is not None and prediction.lambda_away is not None:
            ProbabilityInvariantValidator.validate_lambda(prediction.lambda_home, "lambda_home")
            ProbabilityInvariantValidator.validate_lambda(prediction.lambda_away, "lambda_away")

            engine = GoalDistributionEngine()
            derived_matrix = engine.compute_score_matrix(prediction.lambda_home, prediction.lambda_away)

            derived_1x2 = engine.derive_1x2(derived_matrix)
            if abs(ph - derived_1x2.home_win) > tolerance:
                raise ValueError(
                    f"Home win probability mismatch: stored {ph}, derived {derived_1x2.home_win} from lambdas ({prediction.lambda_home}, {prediction.lambda_away})"
                )
            if abs(pd - derived_1x2.draw) > tolerance:
                raise ValueError(
                    f"Draw probability mismatch: stored {pd}, derived {derived_1x2.draw} from lambdas ({prediction.lambda_home}, {prediction.lambda_away})"
                )
            if abs(pa - derived_1x2.away_win) > tolerance:
                raise ValueError(
                    f"Away win probability mismatch: stored {pa}, derived {derived_1x2.away_win} from lambdas ({prediction.lambda_home}, {prediction.lambda_away})"
                )

            if prediction.btts is not None:
                derived_btts = engine.derive_btts(derived_matrix, prediction.lambda_home, prediction.lambda_away)
                if abs(prediction.btts.yes - derived_btts.yes) > tolerance:
                    raise ValueError(
                        f"BTTS Yes mismatch: stored {prediction.btts.yes}, derived {derived_btts.yes}"
                    )
                if abs(prediction.btts.no - derived_btts.no) > tolerance:
                    raise ValueError(
                        f"BTTS No mismatch: stored {prediction.btts.no}, derived {derived_btts.no}"
                    )

            if prediction.over_under_2_5 is not None:
                derived_ou = engine.derive_over_under_2_5(derived_matrix, prediction.lambda_home, prediction.lambda_away)
                if abs(prediction.over_under_2_5.over - derived_ou.over) > tolerance:
                    raise ValueError(
                        f"Over 2.5 mismatch: stored {prediction.over_under_2_5.over}, derived {derived_ou.over}"
                    )
                if abs(prediction.over_under_2_5.under - derived_ou.under) > tolerance:
                    raise ValueError(
                        f"Under 2.5 mismatch: stored {prediction.over_under_2_5.under}, derived {derived_ou.under}"
                    )

            if prediction.most_likely_score is not None:
                derived_mls = engine.most_likely_score(derived_matrix)
                if prediction.most_likely_score != derived_mls:
                    raise ValueError(
                        f"Most likely score mismatch: stored {prediction.most_likely_score}, derived {derived_mls}"
                    )

            if prediction.top_exact_scores:
                derived_top = engine.top_exact_scores(derived_matrix, n=len(prediction.top_exact_scores))
                for idx, (stored_score, derived_score) in enumerate(zip(prediction.top_exact_scores, derived_top)):
                    if stored_score["score_str"] != derived_score["score_str"]:
                        raise ValueError(
                            f"Top score rank {idx+1} score mismatch: stored {stored_score['score_str']}, derived {derived_score['score_str']}"
                        )
                    if abs(stored_score["probability"] - derived_score["probability"]) > tolerance:
                        raise ValueError(
                            f"Top score rank {idx+1} prob mismatch: stored {stored_score['probability']}, derived {derived_score['probability']}"
                        )


class GoalDistributionEngine:
    """
    Central mathematical engine for goal distributions under independent Poisson.
    Decoupled from model parameter estimation.
    """

    def __init__(self, max_goals: int = 10, tail_tolerance: float = 1e-6) -> None:
        self.max_goals = max_goals
        self.tail_tolerance = tail_tolerance

    def validate_lambdas(self, lambda_home: float, lambda_away: float) -> None:
        """Validates expected goal parameters."""
        ProbabilityInvariantValidator.validate_lambda(lambda_home, "lambda_home")
        ProbabilityInvariantValidator.validate_lambda(lambda_away, "lambda_away")

    def compute_score_matrix(
        self, lambda_home: float, lambda_away: float, max_goals: int | None = None, normalize: bool = True, rho: float = 0.0
    ) -> ScoreProbabilityMatrix:
        """
        Computes joint score probability matrix under independent Poisson assumption:
        P(H=i, A=j) = P(H=i) * P(A=j) * tau(i, j)  (where tau is Dixon-Coles correction if rho != 0)
        """
        self.validate_lambdas(lambda_home, lambda_away)
        k = max_goals if max_goals is not None else self.max_goals
        grid_size = k + 1

        h_pmf = [float(poisson.pmf(i, lambda_home)) for i in range(grid_size)]
        a_pmf = [float(poisson.pmf(j, lambda_away)) for j in range(grid_size)]

        raw_matrix = np.outer(h_pmf, a_pmf)
        
        # Apply Dixon-Coles low-score correction tau(x, y) if rho is non-zero
        distribution_family = "INDEPENDENT_POISSON"
        assumptions = ["HomeGoals ⟂ AwayGoals | pre-match features"]
        
        if abs(rho) > 1e-6 and grid_size > 1:
            distribution_family = "DIXON_COLES"
            assumptions.append(f"Low-score dependency (rho={rho:.4f})")
            
            # tau(0, 0) = 1 - lambda_home * lambda_away * rho
            # tau(0, 1) = 1 + lambda_home * rho
            # tau(1, 0) = 1 + lambda_away * rho
            # tau(1, 1) = 1 - rho
            tau_00 = max(0.0, 1.0 - lambda_home * lambda_away * rho)
            tau_01 = max(0.0, 1.0 + lambda_home * rho)
            tau_10 = max(0.0, 1.0 + lambda_away * rho)
            tau_11 = max(0.0, 1.0 - rho)

            raw_matrix[0, 0] *= tau_00
            raw_matrix[0, 1] *= tau_01
            raw_matrix[1, 0] *= tau_10
            raw_matrix[1, 1] *= tau_11

        retained_mass = float(np.sum(raw_matrix))
        tail_mass = float(1.0 - retained_mass)

        if normalize and retained_mass > 0:
            final_matrix = raw_matrix / retained_mass
        else:
            final_matrix = raw_matrix

        matrix_list = final_matrix.tolist()

        return ScoreProbabilityMatrix(
            max_home_goals=k,
            max_away_goals=k,
            grid_size=grid_size,
            matrix=matrix_list,
            retained_probability_mass=round(retained_mass, 6),
            tail_probability_mass=round(max(0.0, tail_mass), 6),
            normalized=normalize,
            distribution_family=distribution_family,
            assumptions=assumptions,
        )

    def derive_1x2(self, score_matrix: ScoreProbabilityMatrix, source_model: str = "") -> OneXTwoProbabilityDTO:
        """Derives 1X2 probabilities by partitioning joint score matrix."""
        arr = np.array(score_matrix.matrix, dtype=np.float64)

        ph = float(np.sum(np.tril(arr, -1)))
        pd = float(np.sum(np.diag(arr)))
        pa = float(np.sum(np.triu(arr, 1)))

        tot = ph + pd + pa
        if tot > 0:
            ph = round(ph / tot, 6)
            pd = round(pd / tot, 6)
            pa = round(1.0 - (ph + pd), 6)

        ProbabilityInvariantValidator.validate_probability_bounds(ph, "prob_home_win")
        ProbabilityInvariantValidator.validate_probability_bounds(pd, "prob_draw")
        ProbabilityInvariantValidator.validate_probability_bounds(pa, "prob_away_win")
        ProbabilityInvariantValidator.validate_sum_to_one(ph + pd + pa, "1X2 sum")

        return OneXTwoProbabilityDTO(
            home_win=ph,
            draw=pd,
            away_win=pa,
            probability_status="RAW_UNCALIBRATED",
            source_model=source_model,
        )

    def derive_btts(
        self, score_matrix: ScoreProbabilityMatrix, lambda_home: float, lambda_away: float, rho: float = 0.0
    ) -> BTTSProbabilityDTO:
        """
        Derives Both Teams To Score (BTTS) probabilities from score matrix
        and performs analytical cross-check under Dixon-Coles modified Poisson:
        P(BTTS Yes) = P_indep(BTTS Yes) - rho * P_indep(1,1)
        """
        arr = np.array(score_matrix.matrix, dtype=np.float64)
        grid_size = score_matrix.grid_size

        # Matrix derived
        matrix_yes = float(np.sum(arr[1:grid_size, 1:grid_size]))
        matrix_yes = min(1.0, max(0.0, matrix_yes))
        matrix_no = round(1.0 - matrix_yes, 6)
        matrix_yes = round(matrix_yes, 6)

        # Analytical cross-check
        analytical_yes_indep = 1.0 - math.exp(-lambda_home) - math.exp(-lambda_away) + math.exp(-(lambda_home + lambda_away))
        p11_indep = lambda_home * lambda_away * math.exp(-(lambda_home + lambda_away))
        analytical_yes = analytical_yes_indep - rho * p11_indep
        
        diff = abs(matrix_yes - analytical_yes)
        # Difference should be bounded by score matrix tail mass + tolerance
        allowed_tol = score_matrix.tail_probability_mass + 1e-4
        if diff > allowed_tol:
            raise ValueError(
                f"BTTS matrix derivation ({matrix_yes}) deviates from analytical ({analytical_yes:.6f}) by {diff:.6f} > allowed {allowed_tol:.6f}"
            )

        ProbabilityInvariantValidator.validate_probability_bounds(matrix_yes, "btts_yes")
        ProbabilityInvariantValidator.validate_probability_bounds(matrix_no, "btts_no")
        ProbabilityInvariantValidator.validate_sum_to_one(matrix_yes + matrix_no, "BTTS sum")

        return BTTSProbabilityDTO(yes=matrix_yes, no=matrix_no, probability_status="RAW_UNCALIBRATED")

    def derive_over_under_2_5(
        self, score_matrix: ScoreProbabilityMatrix, lambda_home: float, lambda_away: float
    ) -> OverUnderProbabilityDTO:
        """
        Derives Over/Under 2.5 probabilities from score matrix
        and performs analytical cross-check under independent Poisson:
        Total Goals H+A ~ Poisson(lh + la)
        """
        arr = np.array(score_matrix.matrix, dtype=np.float64)
        grid_size = score_matrix.grid_size

        # Matrix derived Under 2.5 (i + j <= 2)
        matrix_under = 0.0
        for i in range(grid_size):
            for j in range(grid_size):
                if i + j <= 2:
                    matrix_under += arr[i, j]

        matrix_under = min(1.0, max(0.0, float(matrix_under)))
        matrix_over = round(1.0 - matrix_under, 6)
        matrix_under = round(matrix_under, 6)

        # Analytical Poisson(lh + la) cross-check for total goals <= 2
        lambda_tot = lambda_home + lambda_away
        analytical_under = float(poisson.cdf(2, lambda_tot))

        diff = abs(matrix_under - analytical_under)
        allowed_tol = score_matrix.tail_probability_mass + 1e-4
        if diff > allowed_tol:
            raise ValueError(
                f"O/U 2.5 matrix derivation ({matrix_under}) deviates from analytical ({analytical_under:.6f}) by {diff:.6f} > allowed {allowed_tol:.6f}"
            )

        ProbabilityInvariantValidator.validate_probability_bounds(matrix_over, "over_2_5")
        ProbabilityInvariantValidator.validate_probability_bounds(matrix_under, "under_2_5")
        ProbabilityInvariantValidator.validate_sum_to_one(matrix_over + matrix_under, "O/U 2.5 sum")

        return OverUnderProbabilityDTO(line=2.5, over=matrix_over, under=matrix_under, probability_status="RAW_UNCALIBRATED")

    def top_exact_scores(self, score_matrix: ScoreProbabilityMatrix, n: int = 5) -> list[dict[str, Any]]:
        """
        Returns top N exact score probabilities ordered deterministically by:
        1. probability DESC
        2. home_goals ASC
        3. away_goals ASC
        """
        arr = np.array(score_matrix.matrix, dtype=np.float64)
        grid_size = score_matrix.grid_size

        candidates = []
        for i in range(grid_size):
            for j in range(grid_size):
                p = round(float(arr[i, j]), 6)
                candidates.append((p, i, j))

        # Deterministic sort: -p for DESC, i for ASC, j for ASC
        candidates.sort(key=lambda x: (-x[0], x[1], x[2]))

        results = []
        for rank, (p, h, a) in enumerate(candidates[:n], start=1):
            results.append({
                "rank": rank,
                "home_goals": h,
                "away_goals": a,
                "score_str": f"{h}-{a}",
                "probability": p,
            })
        return results

    def most_likely_score(self, score_matrix: ScoreProbabilityMatrix) -> tuple[int, int]:
        """Returns (home_goals, away_goals) for the score cell with highest probability."""
        top = self.top_exact_scores(score_matrix, n=1)
        return (top[0]["home_goals"], top[0]["away_goals"])

    def total_goals_distribution(
        self, score_matrix: ScoreProbabilityMatrix, lambda_home: float, lambda_away: float, max_k: int = 10
    ) -> dict[int, float]:
        """Returns PMF of total goals (H+A = k) derived from matrix."""
        arr = np.array(score_matrix.matrix, dtype=np.float64)
        grid_size = score_matrix.grid_size

        dist: dict[int, float] = {}
        for k in range(max_k + 1):
            prob_k = 0.0
            for i in range(grid_size):
                for j in range(grid_size):
                    if i + j == k:
                        prob_k += arr[i, j]
            dist[k] = round(float(prob_k), 6)
        return dist
