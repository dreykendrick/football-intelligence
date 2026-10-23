"""
Operational Error Classification, Retries & Circuit Breaker (Sections 27-32)
Strictly separates ErrorCategory from Retryability (two orthogonal dimensions).
Implements bounded exponential backoff and a process-local circuit breaker.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from app.automation.clock import Clock, SystemClock


class ErrorCategory(StrEnum):
    """Failure source category."""
    PROVIDER = "PROVIDER"
    DATABASE = "DATABASE"
    CONFIGURATION = "CONFIGURATION"
    SCIENTIFIC_INTEGRITY = "SCIENTIFIC_INTEGRITY"
    DATA = "DATA"
    INTERNAL = "INTERNAL"


class Retryability(StrEnum):
    """Retry classification."""
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"


class CircuitBreakerState(StrEnum):
    """Circuit breaker operational state."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class OperationalException(Exception):
    """Base exception for operational automation with orthogonal category and retryability."""

    def __init__(
        self,
        category: ErrorCategory,
        retryability: Retryability,
        failure_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"[{category.value}][{retryability.value}][{failure_code}] {message}")
        self.category = category
        self.retryability = retryability
        self.failure_code = failure_code
        self.message = message
        self.details = details or {}


class TransientProviderError(OperationalException):
    def __init__(self, failure_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCategory.PROVIDER, Retryability.TRANSIENT, failure_code, message, details)


class PermanentProviderError(OperationalException):
    def __init__(self, failure_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCategory.PROVIDER, Retryability.PERMANENT, failure_code, message, details)


class TransientDatabaseError(OperationalException):
    def __init__(self, failure_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCategory.DATABASE, Retryability.TRANSIENT, failure_code, message, details)


class PermanentDatabaseError(OperationalException):
    def __init__(self, failure_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCategory.DATABASE, Retryability.PERMANENT, failure_code, message, details)


class ConfigurationError(OperationalException):
    def __init__(self, failure_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCategory.CONFIGURATION, Retryability.PERMANENT, failure_code, message, details)


class ScientificIntegrityError(OperationalException):
    def __init__(self, failure_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCategory.SCIENTIFIC_INTEGRITY, Retryability.PERMANENT, failure_code, message, details)


class DataIntegrityError(OperationalException):
    def __init__(self, failure_code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCategory.DATA, Retryability.PERMANENT, failure_code, message, details)


class RetryPolicy:
    """
    Deterministic bounded exponential backoff policy.
    Never retries PERMANENT failures. Uses injected Clock for time progression.
    """

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay_seconds: float = 1.0,
        backoff_multiplier: float = 2.0,
        max_delay_seconds: float = 30.0,
        clock: Clock | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.initial_delay_seconds = initial_delay_seconds
        self.backoff_multiplier = backoff_multiplier
        self.max_delay_seconds = max_delay_seconds
        self.clock = clock or SystemClock()

    def compute_delay(self, attempt: int) -> float:
        """Calculate exponential delay for attempt index (1-based)."""
        if attempt <= 0:
            return 0.0
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_delay_seconds)

    def should_retry(self, exc: Exception, current_attempt: int) -> bool:
        """Decide whether an exception should be retried."""
        if current_attempt >= self.max_retries:
            return False

        if isinstance(exc, OperationalException):
            return exc.retryability == Retryability.TRANSIENT

        return False


class CircuitBreaker:
    """
    Lightweight process-local circuit breaker for provider and external services.
    Transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.
    Scope: Process-local.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        clock: Clock | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock or SystemClock()

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: datetime | None = None
        self._half_open_successes = 0

    @property
    def state(self) -> CircuitBreakerState:
        now = self.clock.now()
        if self._state == CircuitBreakerState.OPEN and self._last_failure_time is not None:
            if (now - self._last_failure_time).total_seconds() >= self.cooldown_seconds:
                self._state = CircuitBreakerState.HALF_OPEN
        return self._state

    def can_execute(self) -> bool:
        current_state = self.state
        return current_state in (CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN)

    def record_success(self) -> None:
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= 2:
                self._state = CircuitBreakerState.CLOSED
                self._consecutive_failures = 0
                self._half_open_successes = 0
        elif self._state == CircuitBreakerState.CLOSED:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_failure_time = self.clock.now()
        if self._consecutive_failures >= self.failure_threshold or self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
