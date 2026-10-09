#!/usr/bin/env python3
"""
Cross-Platform Development Tasks Script
Usage:
    python scripts/dev_setup.py test
    python scripts/dev_setup.py lint
    python scripts/dev_setup.py migrate
    python scripts/dev_setup.py run
"""
import os
import subprocess
import sys


def run_cmd(cmd, cwd=None):
    print(f"--> Executing: {cmd}")
    res = subprocess.run(cmd, shell=True, cwd=cwd)
    if res.returncode != 0:
        print(f"Command failed with exit code {res.returncode}")
        sys.exit(res.returncode)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")

    if action == "test":
        run_cmd("pytest", cwd=backend_dir)
    elif action == "lint":
        run_cmd("ruff check app tests", cwd=backend_dir)
    elif action == "format":
        run_cmd("ruff format app tests", cwd=backend_dir)
    elif action == "migrate":
        run_cmd("alembic upgrade head", cwd=backend_dir)
    elif action == "run":
        run_cmd("uvicorn app.main:app --reload --port 8000", cwd=backend_dir)
    else:
        print(f"Unknown action: {action}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
