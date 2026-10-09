# Football Intelligence System — Backend API & Engine

This directory contains the Python 3.11+ backend core built with FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, and Pytest.

## Directory Structure

```text
backend/
├── app/
│   ├── api/            # FastAPI Routers & Versioned Endpoints (v1)
│   ├── core/           # Configuration, Structured Logging, Custom Exceptions
│   ├── db/             # SQLAlchemy Engine, Session, Base & ORM Models
│   ├── providers/      # Abstract Provider Protocol Interfaces
│   ├── ingestion/      # Data Parsing & Ingestion Adapters
│   ├── features/       # Feature Engineering & Time-Bounded Calculators
│   ├── models/         # Baseline & Poisson Model Solvers
│   ├── prediction/     # Immutable Prediction Snapshot Generator
│   ├── backtesting/    # Temporal Backtesting Engine & Anti-Leakage Guards
│   ├── evaluation/     # Brier, Log Loss & Calibration Metric Engines
│   ├── registry/       # 5-Stage Model Registry Lifecycle
│   └── automation/     # Runner Scripts & Job Trigger Wrappers
├── alembic/            # Schema Version Migrations
├── tests/              # Pytest Unit & Integration Test Suite
├── alembic.ini         # Alembic Config
└── pyproject.toml      # Dependency & Tool Configuration
```

## Running Tests & Quality Checks

```bash
# Run unit and integration tests
pytest

# Run ruff code linter
ruff check app tests

# Run ruff formatter check
ruff format --check app tests
```

## Migration Commands

```bash
# Apply migrations to latest schema
alembic upgrade head

# Rollback last migration
alembic downgrade -1
```
