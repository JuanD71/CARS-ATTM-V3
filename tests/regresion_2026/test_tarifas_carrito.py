"""El carrito actualiza la tarifa actual y la foto elegida para una unidad nueva."""
import os
from datetime import date, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_cotizacion_y_foto_actualizadas(tmp_path):
    os.environ['DATABASE_URL']='sqlite+pysqlite:///'+str(tmp_path/'cart.sqlite')
    os.environ['INVENTARIO_URL']='http://inventario-service:8000'
    from app.db import Base,engine
    from app.models import Cart,Item
    from app.main import app,current_user
    import app.main as main
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        cart=Cart(usuario_id=42);db.add(cart);db.flush()
        db.add(Item(carrito_id=cart.id,vehiculo_id=41,marca='Auto',linea='Nuevo',precio_dia=100,
            imagen_url='/vehicles/car-01.webp',fecha_inicio=date.today()+timedelta(days=1),
            fecha_fin=date.today()+timedelta(days=3)))
        db.commit()
    class Result:
        status_code=200
        def raise_for_status(self): pass
        def json(self): return {'id':41,'precioDia':230,'imagenUrl':'/vehicles/car-39.webp'}
    class FakeClient:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, *args, **kwargs): return Result()
    app.dependency_overrides[current_user]=lambda:{'id':42,'rol':'cliente'}
    with patch.object(main.httpx, 'Client', FakeClient):
        with TestClient(app) as c:
            r=c.get('/api/v1/carrito')
            assert r.status_code==200
            j=r.json()
            assert j['alquiler']==460
            assert j['deposito']==920
            assert j['total']==1380
            assert j['items'][0]['precioDia']==230
            assert j['items'][0]['imagenUrl']=='/vehicles/car-39.webp'
    app.dependency_overrides.clear()
