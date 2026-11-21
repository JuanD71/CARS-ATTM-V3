from pydantic import ValidationError
import pytest

from app.main import CheckoutIn, tiene_multas_pendientes


def test_checkout_normaliza_contacto():
    data = CheckoutIn(correo=" JUAN@EXAMPLE.COM ", telefono="300 123 4567", documento="1012345678", cuentaBancariaId=7)
    assert data.correo == "juan@example.com"
    assert data.telefono == "3001234567"
    assert data.documento == "1012345678"


@pytest.mark.parametrize("payload", [
    {"correo": "no-es-correo", "telefono": "3001234567", "documento": "1012345678"},
    {"correo": "juan@example.com", "telefono": "123", "documento": "1012345678"},
    {"correo": "juan@example.com", "telefono": "3001234567", "documento": "123"},
])
def test_checkout_rechaza_contacto_invalido(payload):
    with pytest.raises(ValidationError):
        CheckoutIn(**payload, cuentaBancariaId=7)


@pytest.mark.parametrize("estado", ["SOLICITADA", "APROBADA", "PAGO_SOLICITADO"])
def test_multas_pendientes_bloquean_nuevo_alquiler(estado):
    assert tiene_multas_pendientes([{"estado": estado}]) is True


@pytest.mark.parametrize("estado", ["PAGADA", "RECHAZADA"])
def test_multas_resueltas_no_bloquean_nuevo_alquiler(estado):
    assert tiene_multas_pendientes([{"estado": estado}]) is False


def test_no_admite_checkout_sin_cuenta_bancaria():
    with pytest.raises(ValidationError):
        CheckoutIn(correo="juan@example.com", telefono="3001234567", documento="1012345678")
