"""Prueba de escritorio vía HTTP con SQLite: no sustituye integración Docker/PostgreSQL/Kafka."""
import os
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from app.db import Base, engine
from app.main import app, current_user
import app.main as main

ROLE={'id':1012345678,'rol':'cliente'}

class FakeResponse:
    def __init__(self,data=None,status=200):self._data=data;self.status_code=status
    def json(self):return self._data
    def raise_for_status(self):
        if self.status_code >=400:raise main.httpx.HTTPStatusError('error',request=main.httpx.Request('GET','http://x'),response=main.httpx.Response(self.status_code))

class FakeServices:
    calls=[]
    def __init__(self, **kwargs):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def get(self,url,**kwargs):
        self.calls.append(('GET',url))
        if '/usuarios/' in url and url.endswith('/estado'):return FakeResponse({'activo':True,'bloqueadoPorMultas':False})
        if '/cuentas/' in url:
            return FakeResponse({'id':3,'banco':'Bancolombia','ultimos4':'0123','principal':True},200 if url.endswith('/3') else 404)
        if '/multas/mis' in url:return FakeResponse([])
        if '/carrito' in url:
            first=(date.today()+timedelta(days=3)).isoformat()
            second=(date.today()+timedelta(days=6)).isoformat()
            third=(date.today()+timedelta(days=5)).isoformat()
            return FakeResponse({'items':[
                {'vehiculoId':41,'marca':'Car','linea':'One','precioDia':200,'subtotal':600,'imagenUrl':'/vehicles/car-01.webp','fechaInicio':first,'fechaFin':second},
                {'vehiculoId':42,'marca':'Car','linea':'Two','precioDia':150,'subtotal':300,'imagenUrl':'/vehicles/car-02.webp','fechaInicio':first,'fechaFin':third}
            ],'alquiler':900,'deposito':1400,'total':2300,'cantidad':2})
        raise AssertionError(url)
    def post(self,url,**kwargs):
        self.calls.append(('POST',url))
        if '/internal/reservas' in url:
            vid=kwargs['json']['vehiculoId']
            return FakeResponse({'precioDia':200 if vid==41 else 150},201)
        if '/internal/multas' in url:return FakeResponse({'created':True},201)
        raise AssertionError(url)
    def delete(self,url,**kwargs):
        self.calls.append(('DELETE',url))
        return FakeResponse({'deleted':True})


def test_checkout_peritajes_danos_y_rol(tmp_path):
    Base.metadata.create_all(engine)
    os.environ.update({'USUARIOS_URL':'http://usuarios-service:8000','MULTAS_URL':'http://multas-service:8085',
      'CARRITO_URL':'http://carrito-service:8000','INVENTARIO_URL':'http://inventario-service:8000',
      'INTERNAL_API_KEY':'internal_local_12345678901234567890123456'})
    app.dependency_overrides[current_user]=lambda: ROLE
    with TestClient(app) as client, patch.object(main.httpx,'Client',FakeServices):
        payload={'correo':'cliente@example.com','telefono':'3101234567','documento':'1012345678','cuentaBancariaId':3}
        assert client.post('/api/v1/ordenes/checkout',json={**payload,'cuentaBancariaId':7},headers={'Authorization':'Bearer demo'}).status_code==422
        created=client.post('/api/v1/ordenes/checkout',json=payload,headers={'Authorization':'Bearer demo'})
        assert created.status_code==201,created.text
        order=created.json();oid=order['id']
        assert order['alquilerTotal']==900
        assert order['depositoTotal']==1400
        assert order['total']==2300
        assert order['solicitudPago']['banco']=='Bancolombia'
        assert order['solicitudPago']['cuentaUltimos4']=='0123'
        assert sorted(x['deposito'] for x in order['items'])==[600,800]
        ROLE['rol']='vendedor'
        assert client.post(f'/api/v1/ordenes/{oid}/pago/aprobar',json={'observacion':''}).status_code==403
        all_orders=client.get('/api/v1/ordenes').json()
        assert all_orders[0]['solicitudPago']['cuentaUltimos4'] is None
        ROLE['rol']='admin'
        assert client.post(f'/api/v1/ordenes/{oid}/pago/aprobar',json={'observacion':'Aprobación prueba'}).status_code==200
        ROLE['rol']='vendedor'
        inspections=[{'vehiculoId':x,'kilometraje':23000+x,'nivelCombustible':'LLENO',
            'carroceria':'BUENO','interior':'BUENO','llantas':'EXCELENTE','luces':'BUENO','observaciones':'Sin novedades'}
            for x in [41,42]]
        invalid=client.post(f'/api/v1/ordenes/{oid}/entrega',json={'depositoRecibido':True,'inspecciones':inspections[:1]})
        assert invalid.status_code==422,invalid.text
        invalid=client.post(f'/api/v1/ordenes/{oid}/entrega',json={'depositoRecibido':False,'inspecciones':inspections})
        assert invalid.status_code==422,invalid.text
        delivered=client.post(f'/api/v1/ordenes/{oid}/entrega',json={'depositoRecibido':True,'inspecciones':inspections,'observacionDeposito':'Recibido en el pago'})
        assert delivered.status_code==200,delivered.text
        assert delivered.json()['depositoRecibido'] is True
        assert len(delivered.json()['inspecciones'])==2
        returned=client.post(f'/api/v1/ordenes/{oid}/devolucion',json={'depositoDevuelto':False,
            'valorDepositoDevuelto':0,'observacionDeposito':'Pendiente de peritaje',
            'inspecciones':inspections,'observacion':'Daño constatado',
            'danos':[{'vehiculoId':41,'tipo':'CARROCERIA','severidad':'LEVE',
                      'descripcion':'Rayón en la puerta derecha','costoEstimado':125}]})
        assert returned.status_code==200,returned.text
        data=returned.json()
        assert data['depositoDevuelto'] is False
        assert len(data['inspecciones'])==4
        assert data['reportesDanos'][0]['estado']=='PENDIENTE'
        did=data['reportesDanos'][0]['id']
        assert client.get('/api/v1/danos').status_code==403
        ROLE['rol']='admin'
        assert client.post(f'/api/v1/danos/{did}/verificar',json={'aprobado':True,'observacion':'Daño comprobado'}).status_code==200
        assert client.post(f'/api/v1/danos/{did}/verificar',json={'aprobado':False,'observacion':'Revisión tardía'}).status_code==409
        assert client.get('/api/v1/danos').json()[0]['estado']=='VERIFICADO'
        refund=client.post(f'/api/v1/ordenes/{oid}/deposito/devolucion',json={'observacion':'Transferencia simulada confirmada'})
        assert refund.status_code==200,refund.text
        assert refund.json()['depositoDevuelto'] is True
        assert refund.json()['valorDepositoDevuelto']==1400
        assert client.post(f'/api/v1/ordenes/{oid}/deposito/devolucion',json={'observacion':'Intento repetido'}).status_code==409
        assert ('POST','http://multas-service:8085/internal/multas') in FakeServices.calls
    app.dependency_overrides.clear()
