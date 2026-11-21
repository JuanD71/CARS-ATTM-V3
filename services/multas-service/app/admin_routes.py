"""Aprobación obligatoria por ADMIN: tanto multa como pago simulado de la multa."""
from datetime import datetime,timezone
import os
import logging
import httpx
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select, BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Session, Mapped, mapped_column
from app.security import current_user,internal_key,require_role
from app.adapters.outbound.postgres.repository import MultaORM
from app.adapters.outbound.postgres.database import Base
from app.adapters.inbound.kafka.events import CrearMultaEvento
from app.domain.models import TipoMulta
from app.domain.errors import MultaDuplicada

router=APIRouter(tags=['Multas / aprobación administrativa'])

class SolicitudPagoMulta(Base):
    __tablename__='solicitudes_pago_multa'
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    multa_id:Mapped[int]=mapped_column(ForeignKey('multas.id'),nullable=False,index=True)
    usuario_id:Mapped[int]=mapped_column(BigInteger,nullable=False)
    valor:Mapped[float]=mapped_column(Numeric(12,2,asdecimal=False),nullable=False)
    modo:Mapped[str]=mapped_column(String(20),default='SIMULADO',nullable=False)
    estado:Mapped[str]=mapped_column(String(20),default='SOLICITADA',nullable=False)
    solicitada_en:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    revisada_en:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    administrador_id:Mapped[int|None]=mapped_column(BigInteger,nullable=True)
    observacion:Mapped[str]=mapped_column(String(500),default='',nullable=False)

def pago_dict(p:SolicitudPagoMulta):
    return dict(id=p.id,multaId=p.multa_id,usuarioId=p.usuario_id,valor=float(p.valor),
      modo=p.modo,estado=p.estado,solicitadaEn=p.solicitada_en.isoformat(),
      revisadaEn=p.revisada_en.isoformat() if p.revisada_en else None,
      administradorId=p.administrador_id,observacion=p.observacion)


def get_db():
    from app.main import engine
    if engine is None:raise HTTPException(503,'PostgreSQL obligatorio para el flujo de aprobaciones')
    with Session(engine) as db:yield db

class Decision(BaseModel):
    observacion:str=Field(default='',max_length=500)

def data(m:MultaORM):
    return dict(id=m.id,ordenId=m.orden_id,usuarioId=m.usuario_id,tipo=m.tipo,
        precioMulta=float(m.precio_multa),observacion=m.observacion,estado=m.estado,
        creadaEn=m.creada_en.isoformat(),fechaPago=m.fecha_pago.isoformat() if m.fecha_pago else None,
        administradorId=m.admin_id,decididaEn=m.decidida_en.isoformat() if m.decidida_en else None,
        pagoSolicitadoEn=m.pago_solicitado_en.isoformat() if m.pago_solicitado_en else None,
        pagoAdministradorId=m.pago_admin_id,observacionAdmin=m.observacion_admin)

ESTADOS_PENDIENTES = ('SOLICITADA', 'APROBADA', 'PAGO_SOLICITADO')
log = logging.getLogger(__name__)


def sin_multas_pendientes(db: Session, usuario_id: int) -> bool:
    """La decisión no puede reactivar al cliente si le quedan otras multas."""
    cantidad = db.scalar(select(func.count()).select_from(MultaORM).where(
        MultaORM.usuario_id == usuario_id, MultaORM.estado.in_(ESTADOS_PENDIENTES)))
    return cantidad == 0


def quitar_restriccion_si_corresponde(db: Session, usuario_id: int) -> bool:
    """Solo retira el bloqueo de alquiler, nunca un bloqueo manual de acceso."""
    if not sin_multas_pendientes(db, usuario_id):
        return False
    with httpx.Client(timeout=6) as client:
        response = client.post(
            f"{os.environ['USUARIOS_URL'].rstrip('/')}/internal/usuarios/{usuario_id}/desbloquear-multas",
            headers={'X-Internal-Key': os.environ['INTERNAL_API_KEY']})
        response.raise_for_status()
    return True


def locked(db:Session,multa_id:int):
    m=db.scalar(select(MultaORM).where(MultaORM.id==multa_id).with_for_update())
    if not m:raise HTTPException(404,'Multa inexistente')
    return m

@router.post('/internal/multas',status_code=201,dependencies=[Depends(internal_key)])
def solicitar_multa(evento:CrearMultaEvento,db:Session=Depends(get_db)):
    from app.main import service
    # Servicio de dominio original calcula el importe y almacena la solicitud (no aprobada).
    try:
        m=service.crear_desde_evento(evento.ordenId,evento.usuarioId,evento.tipo,
            evento.valorAlquiler,evento.diasRetraso,evento.observacion)
    except MultaDuplicada:raise HTTPException(409,'Ya existe una solicitud de multa de ese tipo para la orden') from None
    return data(db.get(MultaORM,m.id))

@router.get('/api/v1/multas')
def listar(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    return [data(m) for m in db.scalars(select(MultaORM).order_by(MultaORM.id.desc())).all()]

@router.get('/api/v1/multas/mis')
def mis_multas(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    q=select(MultaORM).where(MultaORM.usuario_id==user['id']).order_by(MultaORM.id.desc())
    return [data(m) for m in db.scalars(q).all()]

@router.get('/api/v1/multas/solicitudes-pago')
def solicitudes_pagos(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    return [pago_dict(p) for p in db.scalars(select(SolicitudPagoMulta).order_by(SolicitudPagoMulta.id.desc())).all()]

@router.get('/api/v1/multas/{multa_id}')
def ver(multa_id:int,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    m=db.get(MultaORM,multa_id)
    if not m:raise HTTPException(404,'Multa inexistente')
    if user['rol'] not in ('admin','vendedor') and m.usuario_id!=user['id']:
        raise HTTPException(403,'Multa ajena')
    return data(m)

@router.post('/api/v1/multas/{multa_id}/aprobar')
def aprobar(multa_id:int,decision:Decision,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    m=locked(db,multa_id)
    if m.estado!='SOLICITADA':raise HTTPException(409,'La solicitud de multa ya fue decidida')
    m.estado='APROBADA';m.admin_id=user['id'];m.decidida_en=datetime.now(timezone.utc)
    m.observacion_admin=decision.observacion;db.commit()
    return data(m)

@router.post('/api/v1/multas/{multa_id}/rechazar')
def rechazar(multa_id:int,decision:Decision,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    m=locked(db,multa_id)
    if m.estado!='SOLICITADA':raise HTTPException(409,'La solicitud de multa ya fue decidida')
    m.estado='RECHAZADA';m.admin_id=user['id'];m.decidida_en=datetime.now(timezone.utc)
    m.observacion_admin=decision.observacion;db.commit()
    try:
        quitar_restriccion_si_corresponde(db, m.usuario_id)
    except (httpx.HTTPError, KeyError) as exc:
        log.warning('Falta sincronizar el desbloqueo de %s: %s', m.usuario_id, exc)
    return data(m)

@router.post('/api/v1/multas/{multa_id}/solicitar-pago')
def solicitar_pago(multa_id:int,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    m=locked(db,multa_id)
    if m.usuario_id!=user['id']:raise HTTPException(403,'La multa no corresponde a tu usuario')
    if m.estado!='APROBADA':raise HTTPException(409,'El administrador debe aprobar primero la multa')
    m.estado='PAGO_SOLICITADO';m.pago_solicitado_en=datetime.now(timezone.utc)
    db.add(SolicitudPagoMulta(multa_id=m.id,usuario_id=user['id'],valor=float(m.precio_multa),
        modo='SIMULADO',estado='SOLICITADA',solicitada_en=m.pago_solicitado_en))
    db.commit();return data(m)

@router.post('/api/v1/multas/{multa_id}/pago/aprobar')
def aprobar_pago(multa_id:int,decision:Decision,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    m=locked(db,multa_id)
    if m.estado!='PAGO_SOLICITADO':raise HTTPException(409,'Se requiere solicitud de pago pendiente')
    p=db.scalar(select(SolicitudPagoMulta).where(SolicitudPagoMulta.multa_id==m.id,
        SolicitudPagoMulta.estado=='SOLICITADA').with_for_update())
    if not p:raise HTTPException(409,'No existe solicitud de pago pendiente')
    p.estado='APROBADA';p.revisada_en=datetime.now(timezone.utc)
    p.administrador_id=user['id'];p.observacion=decision.observacion
    m.estado='PAGADA';m.fecha_pago=datetime.now(timezone.utc)
    m.pago_admin_id=user['id'];m.pago_decidido_en=m.fecha_pago
    m.observacion_admin=decision.observacion
    db.commit()
    # Eventos existentes del proyecto: se publican SOLO al aceptar el pago simulado.
    from app.main import service
    try:
        service.publisher.publicar(service.topic_orden_pagada,str(m.orden_id),{
            'multaId':m.id,'ordenId':m.orden_id,'usuarioId':m.usuario_id,
            'precioMulta':float(m.precio_multa),'fechaPago':m.fecha_pago.isoformat()})
    except Exception:
        log.exception('El pago se guardó, pero falló su publicación en Kafka')
    try:
        quitar_restriccion_si_corresponde(db, m.usuario_id)
    except (httpx.HTTPError, KeyError) as exc:
        # El pago está persistido. Esto no altera un bloqueo administrativo.
        log.warning('El pago quedó aprobado; pendiente sincronizar desbloqueo del cliente %s: %s',
                    m.usuario_id, exc)
    return data(m)

@router.post('/api/v1/multas/{multa_id}/pago/rechazar')
def rechazar_pago(multa_id:int,decision:Decision,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    m=locked(db,multa_id)
    if m.estado!='PAGO_SOLICITADO':raise HTTPException(409,'Se requiere solicitud de pago pendiente')
    p=db.scalar(select(SolicitudPagoMulta).where(SolicitudPagoMulta.multa_id==m.id,
        SolicitudPagoMulta.estado=='SOLICITADA').with_for_update())
    if not p:raise HTTPException(409,'No existe solicitud de pago pendiente')
    p.estado='RECHAZADA';p.revisada_en=datetime.now(timezone.utc)
    p.administrador_id=user['id'];p.observacion=decision.observacion
    m.estado='APROBADA' # Permite volver a solicitar pago; la solicitud rechazada queda en historial.
    m.pago_admin_id=user['id'];m.pago_decidido_en=datetime.now(timezone.utc)
    m.observacion_admin=decision.observacion
    db.commit();return data(m)



@router.post('/api/v1/multas/usuarios/{usuario_id}/sincronizar-restriccion')
def sincronizar_restriccion(usuario_id: int, user: dict = Depends(current_user),
                           db: Session = Depends(get_db)):
    """Reintento administrativo seguro si falla Usuarios al aprobar un pago."""
    require_role(user, 'admin')
    if not sin_multas_pendientes(db, usuario_id):
        raise HTTPException(409, 'El cliente todavía tiene multas pendientes')
    try:
        desbloqueado = quitar_restriccion_si_corresponde(db, usuario_id)
    except (httpx.HTTPError, KeyError):
        raise HTTPException(503, 'Usuarios no disponible para sincronizar la restricción') from None
    return {'usuarioId': usuario_id, 'restriccionPorMultas': not desbloqueado}
