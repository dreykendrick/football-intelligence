"""
Operational Automation Package (Sprint 7.1)
Unattended orchestration, distributed lease management with monotonic fencing tokens,
injectable UTC clocks, retry policies, and health diagnostics.
"""
from app.automation.clock import Clock, FakeClock, SystemClock
from app.automation.domain import (
    DueWorkItem,
    DueWorkType,
    ExecutionMode,
    HealthStatusDTO,
    OperationalHealthState,
    OperationalRunStatus,
    OperationalRunSummary,
)
from app.automation.errors import (
    CircuitBreaker,
    CircuitBreakerState,
    ConfigurationError,
    ErrorCategory,
    OperationalException,
    PermanentDatabaseError,
    PermanentProviderError,
    Retryability,
    RetryPolicy,
    ScientificIntegrityError,
    TransientDatabaseError,
    TransientProviderError,
)
from app.automation.health import HealthWatchdog
from app.automation.lease import LeaseManager, LeaseRecord
from app.automation.orchestrator import OperationalOrchestrator

__all__ = [
    "Clock",
    "SystemClock",
    "FakeClock",
    "ExecutionMode",
    "OperationalRunStatus",
    "OperationalHealthState",
    "DueWorkType",
    "DueWorkItem",
    "OperationalRunSummary",
    "HealthStatusDTO",
    "ErrorCategory",
    "Retryability",
    "CircuitBreakerState",
    "OperationalException",
    "TransientProviderError",
    "PermanentProviderError",
    "TransientDatabaseError",
    "PermanentDatabaseError",
    "ConfigurationError",
    "ScientificIntegrityError",
    "RetryPolicy",
    "CircuitBreaker",
    "LeaseRecord",
    "LeaseManager",
    "HealthWatchdog",
    "OperationalOrchestrator",
]
