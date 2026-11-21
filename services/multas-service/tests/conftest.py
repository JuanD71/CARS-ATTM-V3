"""Configuración aislada de pruebas: SQLite y dobles solo si faltan extras opcionales."""
import os
import sys
import tempfile
from pathlib import Path
import types

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

os.environ["DATABASE_URL"] = (
    "sqlite+pysqlite:///" + str(Path(tempfile.gettempdir()) / f"carsattm_multas_tests_{os.getpid()}.sqlite")
)
os.environ["KAFKA_ENABLED"] = "false"
os.environ["KAFKA_CONSUMER_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "secret_for_local_multas_tests_32_bytes_minimum"
os.environ["INTERNAL_API_KEY"] = "internal_for_local_multas_tests_32_bytes"
os.environ["USUARIOS_URL"] = "http://usuarios-service:8000"

try:
    import confluent_kafka  # noqa: F401
except ModuleNotFoundError:
    kafka = types.ModuleType("confluent_kafka")
    kafka.Consumer = type("Consumer", (), {})
    kafka.Producer = type("Producer", (), {})
    sys.modules["confluent_kafka"] = kafka

try:
    import prometheus_fastapi_instrumentator  # noqa: F401
except ModuleNotFoundError:
    prometheus = types.ModuleType("prometheus_fastapi_instrumentator")

    class Instrumentator:
        def instrument(self, app):
            return self

        def expose(self, app, endpoint=None):
            return self

    prometheus.Instrumentator = Instrumentator
    sys.modules["prometheus_fastapi_instrumentator"] = prometheus
