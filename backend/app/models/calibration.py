import numpy as np
import math
from typing import Any
from sklearn.linear_model import LogisticRegression

class ProbabilityCalibrator:
    """
    Multinomial Logistic Calibration for 1X2 probabilities.
    Transforms raw probabilities into logits, and fits a multinomial logistic regression
    to map them to empirical frequencies.
    """
    def __init__(self, method: str = "MULTINOMIAL_LOGISTIC"):
        self.method = method
        self.model = LogisticRegression(solver="lbfgs", max_iter=1000)
        self.is_fitted = False

    def fit(self, X_probs: np.ndarray, y_true: np.ndarray) -> None:
        """
        X_probs: array of shape (N, 3) where cols are P(Home), P(Draw), P(Away).
        y_true: array of shape (N,) with categorical labels (e.g. 'HOME_WIN', 'DRAW', 'AWAY_WIN' or 0,1,2).
        """
        eps = 1e-10
        X_logits = np.log(np.clip(X_probs, eps, 1 - eps))
        self.model.fit(X_logits, y_true)
        self.is_fitted = True

    def calibrate(self, X_probs: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("ProbabilityCalibrator is not fitted.")
        eps = 1e-10
        X_logits = np.log(np.clip(X_probs, eps, 1 - eps))
        return self.model.predict_proba(X_logits)

    def get_payload(self) -> dict[str, Any]:
        if not self.is_fitted:
            return {}
        return {
            "method": self.method,
            "coef": self.model.coef_.tolist(),
            "intercept": self.model.intercept_.tolist(),
            "classes": self.model.classes_.tolist()
        }

    def load_payload(self, payload: dict[str, Any]) -> None:
        if not payload:
            return
        self.method = payload.get("method", "MULTINOMIAL_LOGISTIC")
        self.model.coef_ = np.array(payload["coef"])
        self.model.intercept_ = np.array(payload["intercept"])
        self.model.classes_ = np.array(payload["classes"])
        self.is_fitted = True
