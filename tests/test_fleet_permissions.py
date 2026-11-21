"""Autorización real en API Inventario, estados y bitácora (SQLite aislado)."""
import os,sys,tempfile,datetime,jwt
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'services'/'inventario-service'))
os.environ['DATABASE_URL']='sqlite+pysqlite:///'+tempfile.mktemp(suffix='.db')
os.environ['JWT_SECRET']='secret_for_local_backend_tests_32_bytes_xxx'
os.environ['INTERNAL_API_KEY']='internal_for_local_backend_tests_32_bytes'
from app.main import app

def auth(role,uid=555):
 now=datetime.datetime.now(datetime.timezone.utc)
 token=jwt.encode({'sub':str(uid),'role':role,'name':'tester','iat':now,'exp':now+datetime.timedelta(minutes=30)},os.environ['JWT_SECRET'],algorithm='HS256')
 return {'Authorization':'Bearer '+token}
admin=auth('admin',557); vendedor=auth('vendedor',556); cliente=auth('cliente',555)
new=dict(placa='DEMOO1',marca='Mazda',linea='CX-5',modelo=2025,categoria='SUV',combustible='Gasolina',transmision='Automática',puestos=5,color='Azul',maletas=4,precioDia=220000,descripcion='Auto de pruebas',imagenUrl='/vehicles/car-01.webp')
class FakeStatus:
 def __init__(self,uid): self.uid=uid;self.status_code=200
 def raise_for_status(self): pass
 def json(self): return {'activo':True,'rol':{555:'cliente',556:'vendedor',557:'admin'}[self.uid]}
def fake_get(url,*args,**kwargs):
 uid=int(url.rstrip('/').split('/')[-2]);return FakeStatus(uid)
os.environ['INTERNAL_API_KEY']='internal_for_local_backend_tests_32_bytes'
os.environ['USUARIOS_URL']='http://usuarios-service:8000'
with patch('app.security.httpx.get',side_effect=fake_get), TestClient(app) as c:
 assert c.get('/api/v1/admin/vehiculos',headers=cliente).status_code==403
 assert c.get('/api/v1/admin/vehiculos',headers=vendedor).status_code==403
 assert c.get('/api/v1/admin/vehiculos').status_code==401
 assert c.get('/api/v1/admin/vehiculos',headers=admin).status_code==200
 for role in [cliente,vendedor]:
  assert c.post('/api/v1/vehiculos',headers=role,json=new).status_code==403
  assert c.put('/api/v1/vehiculos/1',headers=role,json=new).status_code==403
  assert c.patch('/api/v1/vehiculos/1/estado',headers=role,json={'estado':'MANTENIMIENTO'}).status_code==403
  assert c.delete('/api/v1/vehiculos/1',headers=role).status_code==403
 res=c.post('/api/v1/vehiculos',headers=admin,json=new);assert res.status_code==201,res.text
 vid=res.json()['id']
 assert res.json()['estado']=='DISPONIBLE'
 assert len(c.get('/api/v1/vehiculos').json())==1
 assert c.patch(f'/api/v1/vehiculos/{vid}/estado',headers=admin,json={'estado':'INVALIDO'}).status_code==422
 d1=(datetime.date.today()+datetime.timedelta(days=5)).isoformat()
 d2=(datetime.date.today()+datetime.timedelta(days=8)).isoformat()
 r=c.post('/internal/reservas',headers={'X-Internal-Key':os.environ['INTERNAL_API_KEY']},json={'ordenId':102,'vehiculoId':vid,'fechaInicio':d1,'fechaFin':d2});assert r.status_code==201,r.text
 r=c.patch(f'/api/v1/vehiculos/{vid}/estado',headers=admin,json={'estado':'MANTENIMIENTO'})
 assert r.status_code==409,r.text
 assert c.delete(f'/internal/reservas/102',headers={'X-Internal-Key':os.environ['INTERNAL_API_KEY']}).status_code==200
 r=c.patch(f'/api/v1/vehiculos/{vid}/estado',headers=admin,json={'estado':'MANTENIMIENTO','observacion':'Taller preventivo'})
 assert r.status_code==200,r.text
 assert r.json()['estado']=='MANTENIMIENTO'
 assert c.get('/api/v1/vehiculos').json()==[]
 assert c.get(f'/api/v1/vehiculos/{vid}').status_code==404
 assert c.post('/internal/reservas',headers={'X-Internal-Key':os.environ['INTERNAL_API_KEY']},json={'ordenId':103,'vehiculoId':vid,'fechaInicio':d1,'fechaFin':d2}).status_code==409
 r=c.put(f'/api/v1/vehiculos/{vid}',headers=admin,json={**new,'precioDia':240000});assert r.status_code==200,r.text
 assert r.json()['precioDia']==240000
 r=c.patch(f'/api/v1/vehiculos/{vid}/estado',headers=admin,json={'estado':'DISPONIBLE'})
 assert r.status_code==200,r.text
 assert len(c.get('/api/v1/vehiculos').json())==1
 assert c.delete(f'/api/v1/vehiculos/{vid}',headers=admin).status_code==204
 assert len(c.get('/api/v1/vehiculos').json())==0
 assert len(c.get('/api/v1/admin/vehiculos',headers=admin).json())==1
 audit=c.get('/api/v1/admin/vehiculos/movimientos',headers=admin);assert audit.status_code==200,audit.text
 assert len(audit.json())==5,audit.text
 assert all(m['administradorId']==557 for m in audit.json())
 assert c.get('/api/v1/admin/vehiculos/movimientos',headers=vendedor).status_code==403
print('PASS inventario: 5 mutaciones con auditoría, estados, autorizaciones y conflictos de reservas')
