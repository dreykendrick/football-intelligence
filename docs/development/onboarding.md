# Developer Onboarding Guide

## Quick Start (9-Step Local Execution Flow)

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/your-org/football-intelligence-system.git
   cd football-intelligence-system
   ```

2. **Create Python Virtual Environment:**
   ```bash
   python -m venv .venv
   ```

3. **Activate Virtual Environment:**
   - Windows (PowerShell): `.venv\Scripts\Activate.ps1`
   - Linux/macOS: `source .venv/bin/activate`

4. **Install Backend Dependencies:**
   ```bash
   pip install -e "./backend[dev]"
   ```

5. **Configure Environment Variables:**
   ```bash
   copy .env.example .env   # On Windows
   # cp .env.example .env   # On Linux/macOS
   ```

6. **Start Local PostgreSQL Database:**
   ```bash
   docker-compose -f infrastructure/docker-compose.yml up -d
   ```

7. **Run Alembic Schema Migrations:**
   ```bash
   cd backend
   alembic upgrade head
   ```

8. **Start FastAPI Local Development Server:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

9. **Verify System Health & Run Tests:**
   - Open browser / curl: `http://localhost:8000/api/v1/health`
   - Execute test suite: `pytest`
   - Execute linter: `ruff check app tests`
