"""Un vendedor ve el seguimiento de órdenes sin los contactos del checkout."""
import os
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_contacto_solo_admin_y_imagen_historica(tmp_path):
    # Usar un sqlite local efímero; Base/engine son cargados al importar app.*.
    os.environ['DATABASE_URL'] = 'sqlite+pysqlite:///' + str(tmp_path / 'orders.sqlite')
    from app.db import Base, engine
    from app.models import Order, PaymentRequest, Detail
    from app.main import app, current_user
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        o=Order(usuario_id=101,estado='PAGO_SOLICITADO',total=100)
        db.add(o);db.flush()
        db.add(PaymentRequest(orden_id=o.id,usuario_id=101,valor=100,modo='SIMULADO',estado='SOLICITADA',
            correo_contacto='private@cars.com',telefono_contacto='3015555555',documento_contacto='101'))
        db.add(Detail(orden_id=o.id,vehiculo_id=42,descripcion='Auto de prueba',fecha_inicio=date.today(),
            fecha_fin=date.today()+timedelta(days=1),precio_dia=100,subtotal=100,imagen_url='/vehicles/car-18.webp'))
        db.commit()
    with TestClient(app) as c:
        app.dependency_overrides[current_user]=lambda:{'id':123,'rol':'vendedor'}
        result=c.get('/api/v1/ordenes')
        assert result.status_code == 200
        x=result.json()[0]
        for field in ('correoContacto','telefonoContacto','documentoContacto'):
            assert x['solicitudPago'][field] is None
        assert x['items'][0]['imagenUrl']=='/vehicles/car-18.webp'
        app.dependency_overrides[current_user]=lambda:{'id':125,'rol':'admin'}
        result=c.get('/api/v1/ordenes')
        assert result.status_code == 200
        assert result.json()[0]['solicitudPago']['correoContacto']=='private@cars.com'
        app.dependency_overrides.clear()
