"""Pruebas aisladas de Inventario, Carrito u Órdenes con SQLite y servicios simulados."""
import datetime
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

name = sys.argv[1]
if name not in {"inventario-service", "carrito-service", "ordenes-service"}:
    raise SystemExit("Uso: python tests/check_service.py inventario-service|carrito-service|ordenes-service")

root = Path(__file__).resolve().parents[1]
service_root = root / "services" / name
sys.path.insert(0, str(service_root))
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///" + tempfile.mktemp(suffix=".db")
os.environ["JWT_SECRET"] = "secret_for_local_backend_tests_32_bytes_xxx"
os.environ["INTERNAL_API_KEY"] = "internal_for_local_backend_tests_32_bytes"
os.environ.update(
    USUARIOS_URL="http://users",
    INVENTARIO_URL="http://inventory",
    CARRITO_URL="http://cart",
    MULTAS_URL="http://fines",
)

from app.main import app  # noqa: E402
import app.security as security  # noqa: E402

ROLES = {12345: "cliente", 556: "vendedor", 557: "admin"}


def auth(role="cliente", user=12345):
    now = datetime.datetime.now(datetime.timezone.utc)
    token = jwt.encode(
        {"sub": str(user), "role": role, "name": role, "iat": now,
         "exp": now + datetime.timedelta(minutes=30)},
        os.environ["JWT_SECRET"], algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


class UserResponse:
    status_code = 200

    def __init__(self, user_id):
        self.user_id = user_id

    def json(self):
        return {"activo": True, "rol": ROLES.get(self.user_id, "cliente"), "bloqueadoPorMultas": False}

    def raise_for_status(self):
        return None


def fake_user_get(url, *args, **kwargs):
    user_id = int(url.rstrip("/").split("/")[-2])
    return UserResponse(user_id)


class Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP failure in fake service")


start = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
end = (datetime.date.today() + datetime.timedelta(days=4)).isoformat()


class FakeClient:
    def __init__(self, timeout=12):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        if "users/" in url or "/usuarios/" in url:
            return Response({"activo": True, "bloqueadoPorMultas": False})
        if "multas/mis" in url:
            return Response([])
        if "cart" in url:
            return Response({"total": 570000, "cantidad": 1, "items": [
                {"vehiculoId": 1, "marca": "Toyota", "linea": "Corolla", "precioDia": 190000,
                 "subtotal": 570000, "fechaInicio": start, "fechaFin": end,
                 "imagenUrl": "/vehicles/car-01.webp"}
            ]})
        if "/vehiculos/" in url and url.rstrip("/").split("/")[-1].isdigit():
            return Response({"id": 1, "marca": "Toyota", "linea": "Corolla", "precioDia": 190000,
                             "imagenUrl": "/vehicles/car-01.webp"})
        if "inventory" in url or "vehiculos" in url:
            return Response([{"id": 1, "marca": "Toyota", "linea": "Corolla", "precioDia": 190000,
                              "imagenUrl": "/vehicles/car-01.webp"}])
        return Response({})

    def post(self, url, **kwargs):
        if "internal/reservas" in url:
            return Response({"reservado": True, "precioDia": 190000.0}, 201)
        return Response({"ok": True}, 201)

    def delete(self, url, **kwargs):
        return Response({"ok": True})


with patch.object(security.httpx, "get", side_effect=fake_user_get), TestClient(app) as client:
    assert client.get("/health").status_code == 200

    if name == "inventario-service":
        vehicle = dict(placa="DEMOO1", marca="Mazda", linea="CX-5", modelo=2025,
                       categoria="SUV", combustible="Gasolina", transmision="Automática",
                       puestos=5, color="Azul", maletas=4, precioDia=220000,
                       descripcion="Auto de pruebas", imagenUrl="/vehicles/car-01.webp")
        assert client.get("/api/v1/admin/vehiculos", headers=auth("cliente")).status_code == 403
        response = client.post("/api/v1/vehiculos", headers=auth("admin", 557), json=vehicle)
        assert response.status_code == 201, response.text
        assert len(client.get("/api/v1/vehiculos").json()) == 1
        assert client.post("/api/v1/vehiculos", headers=auth("cliente"), json={**vehicle, "placa": "BAD111"}).status_code == 403

    elif name == "carrito-service":
        assert client.get("/api/v1/carrito", headers=auth()).json()["items"] == []
        with patch("app.main.httpx.Client", FakeClient):
            response = client.post("/api/v1/carrito/elementos", headers=auth(),
                                   json={"vehiculoId": 1, "fechaInicio": start, "fechaFin": end})
            assert response.status_code == 201, response.text
            assert client.get("/api/v1/carrito", headers=auth()).json()["cantidad"] == 1
            duplicate = client.post("/api/v1/carrito/elementos", headers=auth(),
                                    json={"vehiculoId": 1, "fechaInicio": start, "fechaFin": end})
            assert duplicate.status_code == 409

    elif name == "ordenes-service":
        assert client.get("/api/v1/ordenes/mis", headers=auth()).json() == []
        with patch("app.main.httpx.Client", FakeClient):
            response = client.post(
                "/api/v1/ordenes/checkout", headers=auth(),
                json={"correo": "cliente@example.com", "telefono": "3001234567", "documento": "12345"},
            )
            assert response.status_code == 201, response.text
            order = response.json()
            assert order["estado"] == "PAGO_SOLICITADO"
            assert order["solicitudPago"]["estado"] == "SOLICITADA"
            assert client.post(f"/api/v1/ordenes/{order['id']}/entrega", headers=auth("vendedor", 556)).status_code == 409
            denied = client.post(f"/api/v1/ordenes/{order['id']}/pago/aprobar", headers=auth("cliente"), json={})
            assert denied.status_code == 403
            approved = client.post(f"/api/v1/ordenes/{order['id']}/pago/aprobar", headers=auth("admin", 557), json={"observacion": "Prueba"})
            assert approved.status_code == 200, approved.text
            delivered = client.post(f"/api/v1/ordenes/{order['id']}/entrega", headers=auth("vendedor", 556))
            assert delivered.status_code == 200, delivered.text
            returned = client.post(f"/api/v1/ordenes/{order['id']}/devolucion", headers=auth("vendedor", 556),
                                   json={"danos": False, "observacion": "Sin novedades"})
            assert returned.status_code == 200, returned.text

print("PASS", name)
