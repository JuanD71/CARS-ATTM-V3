"""JWT firmado no sustituye la consulta al usuario actual de PostgreSQL."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('mock HTTP error')


@pytest.mark.parametrize('service', ['ordenes', 'inventario', 'carrito', 'multas'])
def test_no_confia_en_tokens_revocados_ni_roles_viejos(service, monkeypatch):
    key = 'jwt-revision-test-2026-with-32-or-more-bytes'
    monkeypatch.setenv('JWT_SECRET', key)
    monkeypatch.setenv('INTERNAL_API_KEY', 'internal-test-2026-with-32-or-more-bytes')
    monkeypatch.setenv('USUARIOS_URL', 'http://usuarios-service:8000')
    module_path = ROOT / 'services' / f'{service}-service' / 'app' / 'security.py'
    spec = importlib.util.spec_from_file_location(service + '_security_revision', module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    token = jwt.encode({'sub': '5032', 'role': 'admin', 'iat': datetime.now(timezone.utc),
                        'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}, key, algorithm='HS256')
    auth = 'Bearer ' + token
    # Usuario realmente cliente: no puede aprovechar un token con rol admin anterior.
    with patch.object(mod.httpx, 'get', return_value=FakeResponse(payload={'activo': True, 'rol': 'cliente', 'bloqueadoPorMultas': True})):
        u = mod.current_user(auth)
        assert u['rol'] == 'cliente' and u['bloqueadoPorMultas'] is True
    # Administración lo desactiva sin esperar la expiración del JWT.
    with patch.object(mod.httpx, 'get', return_value=FakeResponse(payload={'activo': False, 'rol': 'admin'})):
        with pytest.raises(HTTPException) as e:
            mod.current_user(auth)
        assert e.value.status_code == 403
    # Si se elimina la cuenta, el JWT deja de ser aceptado.
    with patch.object(mod.httpx, 'get', return_value=FakeResponse(status_code=404)):
        with pytest.raises(HTTPException) as e:
            mod.current_user(auth)
        assert e.value.status_code == 401
    # Si Usuarios no responde, falla de forma segura.
    with patch.object(mod.httpx, 'get', side_effect=mod.httpx.ConnectError('usuarios offline')):
        with pytest.raises(HTTPException) as e:
            mod.current_user(auth)
        assert e.value.status_code == 503
