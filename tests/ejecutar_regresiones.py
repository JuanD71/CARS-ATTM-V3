"""Ejecuta las suites de regresión aisladas en procesos separados."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
suite = [
    ("JWT y revocación", None, "tests/regresion_2026/test_jwt_estados.py"),
    ("Usuarios y roles", "usuarios", "services/usuarios-service/tests/test_usuarios_api.py"),
    ("Privacidad de órdenes", "ordenes", "tests/regresion_2026/test_privacidad_ordenes.py"),
    ("Validación checkout", "ordenes", "services/ordenes-service/tests/test_checkout_validation.py"),
    ("Tarifas e imágenes", "carrito", "tests/regresion_2026/test_tarifas_carrito.py"),
    ("Restricción de multas", "multas", "tests/regresion_2026/test_restriccion_multas.py"),
]
errors = []
for title, service, path in suite:
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    if service:
        env["PYTHONPATH"] = str(root / "services" / f"{service}-service")
    print(f"\n=== {title} ===", flush=True)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", path], cwd=root, env=env)
    if result.returncode:
        errors.append(title)

print("\n" + ("ERRORES: " + ", ".join(errors) if errors else "TODAS LAS PRUEBAS DE REGRESIÓN PASARON"))
sys.exit(bool(errors))
