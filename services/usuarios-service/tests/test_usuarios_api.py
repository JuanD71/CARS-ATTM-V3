"""Pruebas de contrato HTTP con repositorio simulado.
No prueban integración real con PostgreSQL/Docker ni el consumidor Kafka.
"""
import importlib.util
import sys
import types
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

RUTA = Path(__file__).resolve().parents[1] / "main.py"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "una_clave_de_prueba_con_48_caracteres_para_jwt_2026")
    monkeypatch.setenv("INTERNAL_API_KEY", "internal_for_local_backend_tests_32_bytes")
    usuarios = {
        1001: {"id": 1001, "nombre": "Cliente Uno", "email": "uno@ejemplo.com", "rol": "cliente", "activo": True},
        1002: {"id": 1002, "nombre": "Vendedor", "email": "vendedor@ejemplo.com", "rol": "vendedor", "activo": True},
        1003: {"id": 1003, "nombre": "Administrador", "email": "admin@ejemplo.com", "rol": "admin", "activo": True},
        1004: {"id": 1004, "nombre": "Bloqueado", "email": "bloqueado@ejemplo.com", "rol": "cliente", "activo": False},
    }

    db_fake = types.ModuleType("db")
    db_fake.comprobar_conexion = lambda: None
    db_fake.asegurar_esquema_restricciones = lambda: None
    db_fake.obtener_usuario = lambda usuario_id: usuarios.get(usuario_id)
    db_fake.listar_usuarios = lambda: list(usuarios.values())
    db_fake.obtener_activo = lambda usuario_id: usuarios.get(usuario_id, {}).get("activo")
    db_fake.autorizacion_usuario = lambda uid: ({**usuarios[uid], 'bloqueado_por_multas': usuarios[uid].get('bloqueado_por_multas', False)} if uid in usuarios else None)
    db_fake.cambiar_restriccion_multas = lambda uid,blocked: (usuarios[uid].update(bloqueado_por_multas=blocked) or True) if uid in usuarios else False
    db_fake.cambiar_estado = lambda uid,active: (usuarios[uid].update(activo=active) or True) if uid in usuarios else False

    accounts={1001:[{'id':10,'banco':'Bancolombia','ultimos4':'4567','principal':True}]}
    def crear_usuario(usuario_id, nombre, email, password, rol="cliente", banco=None, numero_cuenta=None):
        if usuario_id in usuarios:
            raise fake_psycopg.IntegrityError()
        usuario = {"id": usuario_id, "nombre": nombre, "email": email, "rol": rol, "activo": True}
        usuarios[usuario_id] = usuario
        if rol=='cliente' and banco and numero_cuenta:
            accounts[usuario_id]=[{'id':42,'banco':banco,'ultimos4':numero_cuenta[-4:],'principal':True}]
        return usuario

    def validar_credenciales(identificador, password):
        if password != "Test1234":
            return None
        return next((u for u in usuarios.values()
                     if identificador.lower() == u["email"].lower() or identificador == str(u["id"])), None)

    def actualizar_usuario(usuario_id, nombre, email):
        usuario = usuarios.get(usuario_id)
        if usuario:
            usuario.update(nombre=nombre, email=email)
        return usuario

    def eliminar_usuario(usuario_id):
        return usuarios.pop(usuario_id, None) is not None

    db_fake.crear_usuario = crear_usuario
    db_fake.listar_cuentas=lambda uid: accounts.get(uid,[])
    def fake_add(uid,bank,number):
        if any(x['banco']==bank and x['ultimos4']==number[-4:] for x in accounts.get(uid,[])):
            raise fake_psycopg.IntegrityError()
        a={'id':len(accounts.get(uid,[]))+20,'banco':bank,'ultimos4':number[-4:],'principal':False}
        accounts.setdefault(uid,[]).append(a)
        return a
    db_fake.crear_cuenta=fake_add
    db_fake.verificar_cuenta=lambda uid,cid: next((x for x in accounts.get(uid,[]) if x['id']==cid),None)

    db_fake.validar_credenciales = validar_credenciales
    db_fake.actualizar_usuario = actualizar_usuario
    db_fake.eliminar_usuario = eliminar_usuario
    monkeypatch.setitem(sys.modules, "db", db_fake)

    consumer_fake = types.ModuleType("consumer")
    consumer_fake.iniciar = lambda: None
    consumer_fake.detener = lambda: None
    monkeypatch.setitem(sys.modules, "consumer", consumer_fake)

    class FakeIntegrityError(Exception):
        pass

    fake_psycopg = types.ModuleType("psycopg2")
    fake_psycopg.IntegrityError = FakeIntegrityError
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg)

    spec = importlib.util.spec_from_file_location("cars_usuarios_test", RUTA)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with TestClient(module.app) as client:
        yield client, usuarios


def token(client, email):
    result = client.post("/api/auth/login", json={"userName": email, "password": "Test1234"})
    assert result.status_code == 200, result.text
    return {"Authorization": "Bearer " + result.json()["token"]}


def test_registro_publico_y_roles(api):
    client, usuarios = api
    registro = client.post("/usuarios", json={"id": 2010, "nombre": "Cliente Nuevo", "email": "nuevo@ejemplo.com", "password": "Segura123", "banco":"Bancolombia", "numeroCuenta":"987654321012"})
    assert registro.status_code == 201, registro.text
    assert registro.json()["rol"] == "cliente"
    assert "password" not in registro.text
    assert client.post("/usuarios", json={"id": 2011, "nombre": "Falso Admin", "email": "adminfalso@ejemplo.com", "password": "Segura123", "banco":"Bancolombia", "numeroCuenta":"987654321012", "rol": "admin"}).status_code == 422
    assert client.post("/usuarios", json={"id": 2010, "nombre": "Duplicado", "email": "otro@ejemplo.com", "password": "Segura123", "banco":"Bancolombia", "numeroCuenta":"987654321012"}).status_code == 409


def test_alta_vendedor_solo_admin(api):
    client, usuarios = api
    cliente = token(client, "uno@ejemplo.com")
    admin = token(client, "admin@ejemplo.com")
    payload = {"id": 2012, "nombre": "Vendedor Nuevo", "email": "vendedor.nuevo@ejemplo.com", "password": "Segura123"}
    assert client.post("/usuarios/vendedores", json=payload, headers=cliente).status_code == 403
    response = client.post("/usuarios/vendedores", json=payload, headers=admin)
    assert response.status_code == 201, response.text
    assert response.json()["rol"] == "vendedor"
    assert usuarios[2012]["rol"] == "vendedor"
    assert client.post("/usuarios/vendedores", json={**payload, "id": 2013, "rol": "admin"}, headers=admin).status_code == 422


def test_login_jwt_y_credenciales(api):
    client, _ = api
    assert client.post("/api/auth/login", json={"userName": "uno@ejemplo.com", "password": "mala"}).status_code == 401
    assert client.post("/api/auth/login", json={"userName": "bloqueado@ejemplo.com", "password": "Test1234"}).status_code == 403
    response = client.post("/api/auth/login", json={"userName": "1001", "password": "Test1234"})
    assert response.status_code == 200
    token_str = response.json()["token"]
    payload = jwt.decode(token_str, "una_clave_de_prueba_con_48_caracteres_para_jwt_2026", algorithms=["HS256"])
    assert payload["sub"] == "1001"
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token_str}).json()["id"] == 1001
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_permisos_sobre_usuarios(api):
    client, usuarios = api
    assert client.get("/usuarios").status_code == 401
    cliente = token(client, "uno@ejemplo.com")
    vendedor = token(client, "vendedor@ejemplo.com")
    admin = token(client, "admin@ejemplo.com")
    assert client.get("/usuarios", headers=cliente).status_code == 403
    assert client.get("/usuarios", headers=admin).status_code == 200
    assert client.get("/usuarios/1002", headers=cliente).status_code == 403
    assert client.get("/usuarios/1001", headers=cliente).status_code == 200
    assert client.get("/usuarios/1001/identidad", headers=vendedor).json() == {"id": 1001, "nombre": "Cliente Uno"}
    assert client.put("/usuarios/1002", json={"nombre": "No", "email": "no@ejemplo.com"}, headers=cliente).status_code == 403
    assert client.put("/usuarios/1001", json={"nombre": "Cambio", "email": "cambio@ejemplo.com", "rol": "admin"}, headers=cliente).status_code == 422
    assert client.delete("/usuarios/1001", headers=cliente).status_code == 403
    assert client.delete("/usuarios/1003", headers=admin).status_code == 409
    usuarios[1005] = {"id": 1005, "nombre": "Otro administrador", "email": "otro.admin@ejemplo.com", "rol": "admin", "activo": True}
    assert client.delete("/usuarios/1005", headers=admin).status_code == 409
    assert client.delete("/usuarios/1001", headers=admin).status_code == 204
    assert client.get("/usuarios/1001", headers=admin).status_code == 404


def test_estado_interno(api):
    client, _ = api
    assert client.get("/usuarios/1004/estado").status_code == 403
    key = {'X-Internal-Key': 'internal_for_local_backend_tests_32_bytes'}
    assert client.get("/usuarios/1004/estado", headers=key).json() == {'usuario_id':1004,'activo':False,'bloqueadoPorMultas':False}
    assert client.get("/usuarios/9999/estado", headers=key).status_code == 404
    blocked = client.post('/internal/usuarios/1001/bloquear', headers=key)
    assert blocked.status_code == 200 and blocked.json()['bloqueadoPorMultas'] is True
    # Restricción por multas: el cliente sigue activo para entrar y pagar.
    assert client.get('/internal/usuarios/1001/autorizacion', headers=key).json()['activo'] is True
    assert client.post('/internal/usuarios/1001/desbloquear-multas', headers=key).status_code == 200


def test_cuentas_bancarias_solo_cliente(api):
    client, _ = api
    cliente=token(client,"uno@ejemplo.com")
    vendedor=token(client,"vendedor@ejemplo.com")
    admin=token(client,"admin@ejemplo.com")
    assert 'Bancolombia' in client.get('/usuarios/bancos').json()
    assert client.get('/usuarios/me/cuentas',headers=admin).status_code==403
    assert client.post('/usuarios/me/cuentas',headers=vendedor,json={
        'banco':'Davivienda','numeroCuenta':'12345678901'}).status_code==403
    assert client.get('/usuarios/me/cuentas',headers=cliente).json()[0]['ultimos4']=='4567'
    added=client.post('/usuarios/me/cuentas',headers=cliente,json={
        'banco':'Davivienda','numeroCuenta':'12345678901'})
    assert added.status_code==201,added.text
    assert added.json()['ultimos4']=='8901'
    assert '12345678901' not in added.text
    assert client.post('/usuarios/me/cuentas',headers=cliente,json={
        'banco':'Banco Imaginario','numeroCuenta':'12345678901'}).status_code==422
    assert client.post('/usuarios/me/cuentas',headers=cliente,json={
        'banco':'Davivienda','numeroCuenta':'ABC123456'}).status_code==422
    key={'X-Internal-Key':'internal_for_local_backend_tests_32_bytes'}
    assert client.get('/internal/usuarios/1001/cuentas/10').status_code==403
    assert client.get('/internal/usuarios/1001/cuentas/10',headers=key).status_code==200
    assert client.get('/internal/usuarios/1002/cuentas/10',headers=key).status_code==404
