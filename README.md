# Football Intelligence & Probability Analysis System

A scientific data-analysis and probability-estimation platform for European football matches.

> **Disclaimer:** This platform is designed strictly for scientific evaluation, statistical research, and probabilistic modeling. It does **not** guarantee match outcomes or provide financial/betting advice.

---

## Current Status: Phase 1 — Development Foundation (Sprint 1.1 Complete)

- **Sprint 0.1:** Product Requirements Document (PRD v0.1.2) Signed Off.
- **Sprint 0.2:** Technical Architecture Specification (v0.2.0) Signed Off.
- **Sprint 1.1:** Monorepo & Backend Foundational Bootstrap Complete.

---

## Architectural Principles

1. **Probability, Not Certainty:** Every match outcome is expressed as a calibrated probability distribution ($P_{\text{Home}}, P_{\text{Draw}}, P_{\text{Away}}$).
2. **Zero Dependency on Bookmaker Odds:** Core prediction engine operates strictly independently from commercial betting markets.
3. **Data Leakage Prevention:** Temporal isolation rules (DL-01 to DL-07) prevent post-kickoff information from entering pre-match features.
4. **Distinct Data Quality & Prediction Uncertainty:** Input data completeness is measured separately from outcome distribution spread.
5. **Immutable Snapshot Ledger:** Pre-match prediction snapshots ($T-24\text{h}, T-6\text{h}, T-90\text{min}$) are append-only.
6. **Comparative Model Evaluation:** Models are evaluated comparatively against Baseline A (Historical Base Rates), Baseline B (Elo-Only), and Baseline C (Basic Poisson).

---

## Monorepo Layout

```text
football-intelligence-system/
├── backend/            # FastAPI, SQLAlchemy 2.0, Alembic, Pytest backend core
├── frontend/           # Next.js 14+ TypeScript dashboard placeholder (MVP-C)
├── data/               # Raw, interim, and processed data directories
├── docs/               # System architecture specs, PRDs, and ADRs
├── infrastructure/     # Docker Compose PostgreSQL local setup
├── scripts/            # Cross-platform development helper scripts
└── .github/            # GitHub Actions CI workflow
```

---

## Quick Start (Local Setup)

### Prerequisites

- Python 3.11+
- PostgreSQL 16 (Native or Docker)
- Git

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/your-org/football-intelligence-system.git
cd football-intelligence-system

python -m venv .venv
# Activate virtual environment:
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -e "./backend[dev]"
```

### 3. Environment Configuration

```bash
copy .env.example .env
```

### 4. Start Local PostgreSQL Database

Using Docker Compose:
```bash
docker-compose -f infrastructure/docker-compose.yml up -d
```

### 5. Run Database Schema Migrations

```bash
cd backend
alembic upgrade head
```

### 6. Run System Health Endpoint & Tests

```bash
# Start local API server
uvicorn app.main:app --reload --port 8000

# Execute Pytest test suite (in another terminal window)
cd backend
pytest

# Execute Linter
ruff check app tests
```

Access health check: `http://localhost:8000/api/v1/health`

---

## Technology Stack

- **Backend:** Python 3.11+, FastAPI 0.110+
- **Database:** PostgreSQL 16
- **ORM & Migrations:** SQLAlchemy 2.0+, Alembic 1.13+
- **Schemas & Parsing:** Pydantic v2
- **Testing & Quality:** Pytest 8.0+, Ruff
- **Frontend (MVP-C):** Next.js 14+, TypeScript, Tailwind CSS

---

## License

Internal Working Repository — All Rights Reserved.
