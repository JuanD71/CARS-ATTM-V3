"""Solo se elimina bloqueo POR MULTAS cuando no quede ninguna multa bloqueante."""
import os
from datetime import datetime, timezone
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_pago_ultima_multa_y_restriccion(tmp_path):
    os.environ['USUARIOS_URL']='http://usuarios-service:8000'
    os.environ['INTERNAL_API_KEY']='s'*32
    from app.admin_routes import sin_multas_pendientes,quitar_restriccion_si_corresponde
    from app.adapters.outbound.postgres.database import Base
    from app.adapters.outbound.postgres.repository import MultaORM
    import app.admin_routes as routes
    engine=create_engine('sqlite+pysqlite:///'+str(tmp_path/'fines.sqlite'))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            MultaORM(orden_id=1,usuario_id=50,tipo='DANOS',precio_multa=100,observacion='a',estado='PAGADA',creada_en=datetime.now(timezone.utc)),
            MultaORM(orden_id=2,usuario_id=50,tipo='RETRASO',precio_multa=50,observacion='b',estado='APROBADA',creada_en=datetime.now(timezone.utc)),
        ]);db.commit()
        assert not sin_multas_pendientes(db,50)
        db.query(MultaORM).filter(MultaORM.estado=='APROBADA').update({'estado':'PAGADA'});db.commit()
        assert sin_multas_pendientes(db,50)
        class Resp:
            def raise_for_status(self): pass
        class Client:
            def __init__(self,**kw): pass
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def post(self,url,headers):
                assert url.endswith('/internal/usuarios/50/desbloquear-multas')
                assert headers['X-Internal-Key']=='s'*32
                return Resp()
        with patch.object(routes.httpx,'Client',Client):
            assert quitar_restriccion_si_corresponde(db,50)
