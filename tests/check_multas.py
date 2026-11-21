"""Ejecuta la suite actual del microservicio de multas desde la raíz del ZIP."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
service = root / "services" / "multas-service"
env = os.environ.copy()
env.pop("DATABASE_URL", None)
env["PYTHONPATH"] = str(service)
result = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "tests"],
    cwd=service,
    env=env,
)
sys.exit(result.returncode)
