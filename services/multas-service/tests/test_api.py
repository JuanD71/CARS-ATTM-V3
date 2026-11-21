from itertools import count

import pytest
from fastapi.testclient import TestClient

from app.admin_routes import quitar_restriccion_si_corresponde
from app.main import app, service
from app.security import current_user
from app.domain.models import TipoMulta

ORDENES = count(7000)
INTERNAL_HEADERS = {"X-Internal-Key": "internal_for_local_multas_tests_32_bytes"}


@pytest.fixture(scope="module")
def client():
    # Ejecuta lifespan: crea el esquema SQLite y cierra el publisher sin Kafka.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def limpiar_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def autenticar(rol: str, usuario_id: int = 1234):
    app.dependency_overrides[current_user] = lambda: {"id": usuario_id, "rol": rol, "activo": True}


def crear_multa(client, usuario_id: int = 1234, orden_id: int | None = None):
    if orden_id is None:
        orden_id = next(ORDENES)
    response = client.post(
        "/internal/multas",
        headers=INTERNAL_HEADERS,
        json={
            "ordenId": orden_id,
            "usuarioId": usuario_id,
            "tipo": "RETRASO",
            "valorAlquiler": 100000,
            "diasRetraso": 2,
            "observacion": "Prueba automatizada",
        },
    )
    return response


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_internal_multas_requiere_clave(client):
    response = client.post(
        "/internal/multas",
        json={"ordenId": 1, "usuarioId": 1234, "tipo": "RETRASO", "valorAlquiler": 100000,
              "diasRetraso": 1, "observacion": "Sin clave"},
    )
    assert response.status_code == 403


def test_crear_multa_y_permisos(client):
    response = crear_multa(client)
    assert response.status_code == 201, response.text
    multa = response.json()
    assert multa["estado"] == "SOLICITADA"
    assert multa["precioMulta"] == 20000

    assert client.get("/api/v1/multas").status_code == 401
    autenticar("cliente", 1234)
    propias = client.get("/api/v1/multas/mis")
    assert propias.status_code == 200
    assert any(item["id"] == multa["id"] for item in propias.json())
    assert client.get(f"/api/v1/multas/{multa['id']}").status_code == 200


def test_multa_duplicada_por_orden_y_tipo(client):
    orden_id = next(ORDENES)
    primera = crear_multa(client, orden_id=orden_id)
    segunda = crear_multa(client, orden_id=orden_id)
    assert primera.status_code == 201, primera.text
    assert segunda.status_code == 409, segunda.text


def test_flujo_aprobar_solicitar_pago_y_confirmar(client, monkeypatch):
    multa_response = crear_multa(client)
    assert multa_response.status_code == 201, multa_response.text
    multa_id = multa_response.json()["id"]

    autenticar("cliente", 1234)
    assert client.post(f"/api/v1/multas/{multa_id}/aprobar", json={}).status_code == 403

    autenticar("admin", 9001)
    aprobada = client.post(f"/api/v1/multas/{multa_id}/aprobar", json={"observacion": "Aprobada en prueba"})
    assert aprobada.status_code == 200, aprobada.text
    assert aprobada.json()["estado"] == "APROBADA"

    autenticar("cliente", 1234)
    solicitud = client.post(f"/api/v1/multas/{multa_id}/solicitar-pago")
    assert solicitud.status_code == 200, solicitud.text
    assert solicitud.json()["estado"] == "PAGO_SOLICITADO"

    autenticar("admin", 9001)
    pagos = client.get("/api/v1/multas/solicitudes-pago")
    assert pagos.status_code == 200
    assert any(pago["multaId"] == multa_id and pago["estado"] == "SOLICITADA" for pago in pagos.json())

    monkeypatch.setattr("app.admin_routes.quitar_restriccion_si_corresponde", lambda db, uid: True)
    pagada = client.post(f"/api/v1/multas/{multa_id}/pago/aprobar", json={"observacion": "Pago validado"})
    assert pagada.status_code == 200, pagada.text
    assert pagada.json()["estado"] == "PAGADA"
    assert client.post(f"/api/v1/multas/{multa_id}/pago/aprobar", json={}).status_code == 409


def test_usuario_no_puede_consultar_multa_ajena(client):
    multa_response = crear_multa(client, usuario_id=1234)
    assert multa_response.status_code == 201
    multa_id = multa_response.json()["id"]
    autenticar("cliente", 5678)
    assert client.get(f"/api/v1/multas/{multa_id}").status_code == 403
