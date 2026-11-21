"""Órdenes y solicitudes de pago. Todas las solicitudes las decide ADMIN."""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, date
import re
from decimal import Decimal
from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload
import httpx
from .db import Base, engine, get_db
from .models import Order, Detail, PaymentRequest, Inspeccion, ReporteDano
from .security import current_user, require_role

@asynccontextmanager
async def lifespan(app:FastAPI):
    Base.metadata.create_all(engine)
    # Migración incremental: añade los datos de contacto a solicitudes ya existentes.
    if engine.dialect.name == 'postgresql':
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE solicitudes_pago ADD COLUMN IF NOT EXISTS correo_contacto VARCHAR(150)"))
            conn.execute(text("ALTER TABLE solicitudes_pago ADD COLUMN IF NOT EXISTS telefono_contacto VARCHAR(24)"))
            conn.execute(text("ALTER TABLE solicitudes_pago ADD COLUMN IF NOT EXISTS documento_contacto VARCHAR(20)"))
            conn.execute(text("ALTER TABLE detalle_orden ADD COLUMN IF NOT EXISTS imagen_url VARCHAR(250)"))
            for table, column, spec in (
                ('ordenes','alquiler_total','NUMERIC(14,2) NOT NULL DEFAULT 0'),
                ('ordenes','deposito_total','NUMERIC(14,2) NOT NULL DEFAULT 0'),
                ('ordenes','deposito_recibido','BOOLEAN NOT NULL DEFAULT FALSE'),
                ('ordenes','deposito_devuelto','BOOLEAN NOT NULL DEFAULT FALSE'),
                ('ordenes','valor_deposito_devuelto','NUMERIC(14,2) NOT NULL DEFAULT 0'),
                ('ordenes','observacion_deposito',"TEXT NOT NULL DEFAULT ''"),
                ('detalle_orden','deposito','NUMERIC(14,2) NOT NULL DEFAULT 0'),
                ('solicitudes_pago','cuenta_bancaria_id','BIGINT'),
                ('solicitudes_pago','banco','VARCHAR(65)'),
                ('solicitudes_pago','cuenta_ultimos4','VARCHAR(4)'),
            ):
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {spec}'))
            # Respeta el valor original de órdenes anteriores sin inventarles depósitos.
            conn.execute(text('UPDATE ordenes SET alquiler_total=total WHERE alquiler_total=0 AND deposito_total=0'))
    yield
app=FastAPI(title='Cars ATTM | Órdenes y pagos',version='2.0.0',lifespan=lifespan)

class CheckoutIn(BaseModel):
    correo: str = Field(min_length=5, max_length=150)
    telefono: str = Field(min_length=7, max_length=24)
    documento: str = Field(min_length=5, max_length=20)
    cuentaBancariaId: int = Field(gt=0)

    @field_validator("correo")
    @classmethod
    def validar_correo(cls, value: str):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Correo electrónico no válido")
        return value

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, value: str):
        digits = re.sub(r"\D", "", value)
        if not 7 <= len(digits) <= 15:
            raise ValueError("Teléfono no válido")
        return digits

    @field_validator("documento")
    @classmethod
    def validar_documento(cls, value: str):
        digits = re.sub(r"\D", "", value)
        if not 5 <= len(digits) <= 15:
            raise ValueError("Documento no válido")
        return digits


class InspeccionIn(BaseModel):
    vehiculoId: int = Field(gt=0)
    kilometraje: int = Field(ge=0, le=2000000)
    nivelCombustible: str = Field(pattern='^(VACIO|CUARTO|MEDIO|TRES_CUARTOS|LLENO)$')
    carroceria: str = Field(pattern='^(EXCELENTE|BUENO|REGULAR|DEFICIENTE)$')
    interior: str = Field(pattern='^(EXCELENTE|BUENO|REGULAR|DEFICIENTE)$')
    llantas: str = Field(pattern='^(EXCELENTE|BUENO|REGULAR|DEFICIENTE)$')
    luces: str = Field(pattern='^(EXCELENTE|BUENO|REGULAR|DEFICIENTE)$')
    observaciones: str = Field(default='', max_length=1000)


class EntregaIn(BaseModel):
    depositoRecibido: bool
    inspecciones: list[InspeccionIn] = Field(min_length=1, max_length=5)
    observacionDeposito: str = Field(default='', max_length=500)


class DanoIn(BaseModel):
    vehiculoId: int = Field(gt=0)
    tipo: str = Field(pattern='^(CARROCERIA|INTERIOR|LLANTAS|LUCES|MECANICO|OTRO)$')
    severidad: str = Field(pattern='^(LEVE|MODERADO|GRAVE)$')
    descripcion: str = Field(min_length=10, max_length=1000)
    costoEstimado: Decimal = Field(default=Decimal('0'), ge=0)


class ReturnIn(BaseModel):
    depositoDevuelto: bool
    valorDepositoDevuelto: Decimal = Field(ge=0)
    observacionDeposito: str = Field(default='', max_length=500)
    inspecciones: list[InspeccionIn] = Field(min_length=1, max_length=5)
    danos: list[DanoIn] = Field(default_factory=list, max_length=5)
    observacion: str = Field(default='', max_length=800)


class ReintegroDepositoIn(BaseModel):
    observacion: str = Field(min_length=5,max_length=500)


class VerificarDanoIn(BaseModel):
    aprobado: bool
    observacion: str = Field(min_length=5,max_length=500)


class DecisionIn(BaseModel):
    observacion:str=Field(default='',max_length=500)

def payment_dict(p: PaymentRequest|None, incluir_contacto: bool = True):
    if not p:return None
    return dict(id=p.id,ordenId=p.orden_id,usuarioId=p.usuario_id,valor=float(p.valor),modo=p.modo,
         estado=p.estado,solicitadaEn=p.solicitada_en.isoformat(),
         revisadaEn=p.revisada_en.isoformat() if p.revisada_en else None,
         administradorId=p.administrador_id,observacion=p.observacion,
         correoContacto=p.correo_contacto if incluir_contacto else None,
         telefonoContacto=p.telefono_contacto if incluir_contacto else None,
         documentoContacto=p.documento_contacto if incluir_contacto else None,
         cuentaBancariaId=p.cuenta_bancaria_id if incluir_contacto else None,
         banco=p.banco if incluir_contacto else None,
         cuentaUltimos4=p.cuenta_ultimos4 if incluir_contacto else None)

def inspecciones_dict(db: Session, order_id: int):
    return [dict(id=i.id,vehiculoId=i.vehiculo_id,tipo=i.tipo,
        kilometraje=i.kilometraje,nivelCombustible=i.nivel_combustible,
        carroceria=i.carroceria,interior=i.interior,llantas=i.llantas,luces=i.luces,
        observaciones=i.observaciones,responsableId=i.responsable_id,
        registradoEn=i.registrado_en.isoformat())
        for i in db.scalars(select(Inspeccion).where(Inspeccion.orden_id==order_id)
                      .order_by(Inspeccion.id)).all()]


def danos_dict(db: Session, order_id: int):
    return [dict(id=d.id,ordenId=d.orden_id,vehiculoId=d.vehiculo_id,tipo=d.tipo,
       severidad=d.severidad,descripcion=d.descripcion,costoEstimado=float(d.costo_estimado),
       estado=d.estado,registradoPor=d.registrado_por,
       registradoEn=d.registrado_en.isoformat(),verificadoPor=d.verificado_por,
       verificadoEn=d.verificado_en.isoformat() if d.verificado_en else None,
       observacionAdmin=d.observacion_admin)
       for d in db.scalars(select(ReporteDano).where(ReporteDano.orden_id==order_id)
                  .order_by(ReporteDano.id)).all()]


def _check_inspections(order: Order, inspecciones: list[InspeccionIn]):
    ids=[i.vehiculoId for i in inspecciones]
    esperados={i.vehiculo_id for i in order.detalles}
    if len(ids)!=len(esperados) or set(ids)!=esperados:
        raise HTTPException(422,'Registra un peritaje para cada vehículo de la orden, sin repetirlos')


def _persist_inspections(db: Session, order: Order, inspections: list[InspeccionIn], tipo: str, actor: int):
    for x in inspections:
        db.add(Inspeccion(orden_id=order.id,vehiculo_id=x.vehiculoId,tipo=tipo,
           kilometraje=x.kilometraje,nivel_combustible=x.nivelCombustible,
           carroceria=x.carroceria,interior=x.interior,llantas=x.llantas,
           luces=x.luces,observaciones=x.observaciones,responsable_id=actor))


def serialize(o:Order, incluir_contacto: bool = True, db: Session|None = None):
    return dict(id=o.id,usuarioId=o.usuario_id,estado=o.estado,total=float(o.total),
        alquilerTotal=float(o.alquiler_total),depositoTotal=float(o.deposito_total),
        depositoRecibido=o.deposito_recibido,depositoDevuelto=o.deposito_devuelto,
        valorDepositoDevuelto=float(o.valor_deposito_devuelto),observacionDeposito=o.observacion_deposito,
        inspecciones=inspecciones_dict(db,o.id) if db else [],
        reportesDanos=danos_dict(db,o.id) if db else [],
        creadaEn=o.creada_en.isoformat(),entregadaEn=o.entregada_en.isoformat() if o.entregada_en else None,
        devueltaEn=o.devuelta_en.isoformat() if o.devuelta_en else None,
        observacionDevolucion=o.observacion_devolucion,reportaDanos=o.reporta_danos,
        vencida=(o.estado=='EN_CURSO' and any(i.fecha_fin<date.today() for i in o.detalles)),
        incumplimiento=(o.estado=='DEVUELTA' and (o.reporta_danos or (o.devuelta_en is not None and any(i.fecha_fin<o.devuelta_en.date() for i in o.detalles)))),
        solicitudPago=payment_dict(o.solicitud_pago, incluir_contacto),
        items=[dict(id=i.id,vehiculoId=i.vehiculo_id,descripcion=i.descripcion,
          fechaInicio=i.fecha_inicio.isoformat(),fechaFin=i.fecha_fin.isoformat(),
          precioDia=float(i.precio_dia),subtotal=float(i.subtotal),deposito=float(i.deposito),imagenUrl=i.imagen_url) for i in o.detalles])

ESTADOS_MULTA_BLOQUEANTES = {'SOLICITADA', 'APROBADA', 'PAGO_SOLICITADO'}

def tiene_multas_pendientes(multas: list[dict]) -> bool:
    """Impide nuevos alquileres mientras haya una multa sin resolver/pagar."""
    return any(m.get('estado') in ESTADOS_MULTA_BLOQUEANTES for m in multas)


def internal_headers():return {'X-Internal-Key':os.environ['INTERNAL_API_KEY']}
def url(name):return os.environ[name].rstrip('/')

def locked(db:Session, oid:int)->Order:
    o=db.scalar(select(Order).options(selectinload(Order.detalles),selectinload(Order.solicitud_pago))
                 .where(Order.id==oid).with_for_update())
    if not o:raise HTTPException(404,'Orden no encontrada')
    return o

@app.get('/health')
def health(db:Session=Depends(get_db)):
    db.execute(text('SELECT 1'));return {'status':'ok'}

@app.post('/api/v1/ordenes/checkout',status_code=201)
def checkout(data:CheckoutIn,user:dict=Depends(current_user),authorization:str=Header(),db:Session=Depends(get_db)):
    require_role(user,'cliente')
    if data.documento != str(user['id']):
        raise HTTPException(422,'El documento debe coincidir con el registrado en tu cuenta')
    try:
        with httpx.Client(timeout=12) as client:
            resp=client.get(f"{url('USUARIOS_URL')}/usuarios/{user['id']}/estado",
                            headers=internal_headers())
            resp.raise_for_status()
            estado_usuario=resp.json()
            resp=client.get(f"{url('USUARIOS_URL')}/internal/usuarios/{user['id']}/cuentas/{data.cuentaBancariaId}",
                headers=internal_headers())
            if resp.status_code==404:raise HTTPException(422,'Selecciona una cuenta de ahorros asociada a tu usuario')
            resp.raise_for_status()
            cuenta=resp.json()
            if not estado_usuario.get('activo'):raise HTTPException(403,'Cuenta desactivada por el administrador')
            if estado_usuario.get('bloqueadoPorMultas'):raise HTTPException(409,'Debes resolver las multas pendientes antes de alquilar')
            # Las multas pendientes aprobadas bloquean nuevas reservas hasta que
            # el administrador confirme el pago. Una multa rechazada o pagada no bloquea.
            fines_resp=client.get(f"{url('MULTAS_URL')}/api/v1/multas/mis",
                                  headers={'Authorization':authorization})
            fines_resp.raise_for_status()
            if tiene_multas_pendientes(fines_resp.json()):
                raise HTTPException(409,'No puedes solicitar nuevos vehículos mientras tengas multas pendientes de pago.')
            resp=client.get(f"{url('CARRITO_URL')}/api/v1/carrito",headers={'Authorization':authorization})
            resp.raise_for_status(); cart=resp.json()
    except HTTPException:raise
    except (httpx.HTTPError,KeyError,ValueError):
        raise HTTPException(503,'No se pudo consultar el carrito, las multas o el estado del usuario') from None
    items=cart.get('items',[])
    if not items:raise HTTPException(409,'El carrito está vacío')
    if len(items)>5:raise HTTPException(409,'Límite de cinco vehículos')
    # Depósito por vehículo: siempre cuatro veces la tarifa de un día,
    # independiente de los días alquilados. Se valida en este servicio también.
    alquiler=sum((Decimal(str(i['precioDia'])) * (date.fromisoformat(i['fechaFin']) -
        date.fromisoformat(i['fechaInicio'])).days for i in items),Decimal('0'))
    deposito=sum((Decimal(str(i['precioDia']))*4 for i in items),Decimal('0'))
    total=alquiler+deposito
    if total != Decimal(str(cart['total'])):
        raise HTTPException(409,'El total del carrito no coincide con alquiler más depósito; actualiza el carrito')
    # No hay pasarela real: el pago y el reintegro se registran manualmente.
    o=Order(usuario_id=user['id'],estado='PAGO_SOLICITADO',total=total,
            alquiler_total=alquiler,deposito_total=deposito)
    db.add(o);db.flush()
    db.add(PaymentRequest(orden_id=o.id,usuario_id=user['id'],valor=total,modo='SIMULADO',
        estado='SOLICITADA',correo_contacto=data.correo,telefono_contacto=data.telefono,
        documento_contacto=data.documento,cuenta_bancaria_id=cuenta['id'],
        banco=cuenta['banco'],cuenta_ultimos4=cuenta['ultimos4']))
    try:
        with httpx.Client(timeout=12) as client:
            for item in items:
                response=client.post(f"{url('INVENTARIO_URL')}/internal/reservas",
                  headers=internal_headers(),json={'ordenId':o.id,'vehiculoId':item['vehiculoId'],
                  'fechaInicio':item['fechaInicio'],'fechaFin':item['fechaFin']})
                if response.status_code==409:raise HTTPException(409,'Un vehículo ya fue reservado. Actualiza el carrito.')
                response.raise_for_status()
                # El precio se verifica CONTRA INVENTARIO después de reservar, para
                # impedir confirmar un carrito que quedó desactualizado.
                precio_actual = Decimal(str(response.json()['precioDia']))
                if precio_actual != Decimal(str(item['precioDia'])):
                    raise HTTPException(409, 'La tarifa cambió. Abre de nuevo el carrito y confirma el importe actualizado.')
                db.add(Detail(orden_id=o.id,vehiculo_id=item['vehiculoId'],
                    descripcion=f"{item['marca']} {item['linea']}",fecha_inicio=date.fromisoformat(item['fechaInicio']),
                    fecha_fin=date.fromisoformat(item['fechaFin']),precio_dia=item['precioDia'],subtotal=item['subtotal'],
                    deposito=Decimal(str(item['precioDia']))*4,
                    imagen_url=item.get('imagenUrl')))
            db.commit()
    except (HTTPException,httpx.HTTPError,KeyError,ValueError) as ex:
        db.rollback()
        try:
            with httpx.Client(timeout=8) as client:
                client.delete(f"{url('INVENTARIO_URL')}/internal/reservas/{o.id}",headers=internal_headers())
        except httpx.HTTPError:pass
        if isinstance(ex,HTTPException):raise
        raise HTTPException(503,'No se pudo registrar la orden; comprueba el inventario') from None
    try:
        with httpx.Client(timeout=8) as client:
            client.delete(f"{url('CARRITO_URL')}/internal/carritos/{user['id']}",headers=internal_headers())
    except httpx.HTTPError:pass
    db.refresh(o)
    o=db.scalar(select(Order).options(selectinload(Order.detalles),selectinload(Order.solicitud_pago)).where(Order.id==o.id))
    return serialize(o, db=db)

@app.get('/api/v1/ordenes/mis')
def mias(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    q=select(Order).options(selectinload(Order.detalles),selectinload(Order.solicitud_pago)).where(Order.usuario_id==user['id']).order_by(Order.id.desc())
    return [serialize(o, db=db) for o in db.scalars(q).all()]

@app.get('/api/v1/ordenes')
def todas(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'vendedor','admin')
    q=select(Order).options(selectinload(Order.detalles),selectinload(Order.solicitud_pago)).order_by(Order.id.desc())
    return [serialize(o, incluir_contacto=(user["rol"] == "admin"), db=db) for o in db.scalars(q).all()]

@app.get('/api/v1/ordenes/solicitudes-pago')
def solicitudes_pago(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    q=select(PaymentRequest).order_by(PaymentRequest.solicitada_en.desc())
    return [payment_dict(x) for x in db.scalars(q).all()]

@app.post('/api/v1/ordenes/{orden_id}/pago/aprobar')
def aprobar(orden_id:int,data:DecisionIn,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    o=locked(db,orden_id)
    if o.estado!='PAGO_SOLICITADO' or o.solicitud_pago.estado!='SOLICITADA':
        raise HTTPException(409,'La solicitud ya fue decidida')
    p=o.solicitud_pago;p.estado='APROBADA';p.revisada_en=datetime.now(timezone.utc)
    p.administrador_id=user['id'];p.observacion=data.observacion
    o.estado='PAGADA';db.commit()
    return serialize(o)

@app.post('/api/v1/ordenes/{orden_id}/pago/rechazar')
def rechazar(orden_id:int,data:DecisionIn,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    o=locked(db,orden_id)
    if o.estado!='PAGO_SOLICITADO' or o.solicitud_pago.estado!='SOLICITADA':
        raise HTTPException(409,'La solicitud ya fue decidida')
    p=o.solicitud_pago;p.estado='RECHAZADA';p.revisada_en=datetime.now(timezone.utc)
    p.administrador_id=user['id'];p.observacion=data.observacion
    o.estado='RECHAZADA';db.commit()
    # Libera reserva para que el vehículo pueda alquilarse de nuevo.
    try:
        with httpx.Client(timeout=8) as client:
            r=client.delete(f"{url('INVENTARIO_URL')}/internal/reservas/{o.id}",headers=internal_headers())
            r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503,'La solicitud quedó rechazada, pero falta liberar inventario; revisar logs') from None
    return serialize(o)

@app.post('/api/v1/ordenes/{orden_id}/entrega')
def entregar(orden_id:int,data:EntregaIn,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'vendedor','admin')
    o=locked(db,orden_id)
    if o.estado!='PAGADA':raise HTTPException(409,'Se requiere aprobación administrativa del pago antes de entregar')
    if not data.depositoRecibido:
        raise HTTPException(422,'Confirma la recepción del depósito incluido en el pago aprobado')
    _check_inspections(o,data.inspecciones)
    _persist_inspections(db,o,data.inspecciones,'ENTREGA',user['id'])
    o.deposito_recibido=True
    o.observacion_deposito=data.observacionDeposito
    o.estado='EN_CURSO';o.entregada_en=datetime.now(timezone.utc)
    db.commit()
    return serialize(o,db=db)


@app.post('/api/v1/ordenes/{orden_id}/devolucion')
def devolver(orden_id:int,data:ReturnIn,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'vendedor','admin')
    o=locked(db,orden_id)
    if o.estado!='EN_CURSO':raise HTTPException(409,'Solo se devuelve una orden en curso')
    _check_inspections(o,data.inspecciones)
    total_deposito=Decimal(o.deposito_total)
    if data.depositoDevuelto and data.valorDepositoDevuelto!=total_deposito:
        raise HTTPException(422,'Para marcar el depósito como devuelto registra el valor completo')
    if not data.depositoDevuelto and (data.valorDepositoDevuelto!=0 or not data.observacionDeposito.strip()):
        raise HTTPException(422,'Si el depósito queda pendiente, registra valor 0 y una justificación')
    ids={x.vehiculo_id for x in o.detalles}
    if len(data.danos) != len({d.vehiculoId for d in data.danos}) or any(d.vehiculoId not in ids for d in data.danos):
        raise HTTPException(422,'Solo se admite un reporte de daños por vehículo de la orden')
    now=datetime.now(timezone.utc)
    dias=max(0,(now.date()-max(x.fecha_fin for x in o.detalles)).days)
    # Las multas por daños solo se generan DESPUÉS de la verificación administrativa.
    if dias>0:
        try:
            with httpx.Client(timeout=12) as client:
                resp=client.post(f"{url('MULTAS_URL')}/internal/multas",headers=internal_headers(),json={
                    'ordenId':o.id,'usuarioId':o.usuario_id,'tipo':'RETRASO',
                    'valorAlquiler':float(o.alquiler_total),'diasRetraso':dias,
                    'observacion':f'Retraso de {dias} día(s)'})
                if resp.status_code!=409:resp.raise_for_status()
        except (httpx.HTTPError, KeyError):
            db.rollback();raise HTTPException(503,'No se pudo registrar la multa por retraso') from None
    _persist_inspections(db,o,data.inspecciones,'DEVOLUCION',user['id'])
    for d in data.danos:
        db.add(ReporteDano(orden_id=o.id,vehiculo_id=d.vehiculoId,tipo=d.tipo,
            severidad=d.severidad,descripcion=d.descripcion,costo_estimado=d.costoEstimado,
            estado='PENDIENTE',registrado_por=user['id']))
    o.estado='DEVUELTA';o.devuelta_en=now;o.reporta_danos=bool(data.danos)
    o.observacion_devolucion=data.observacion
    o.deposito_devuelto=data.depositoDevuelto
    o.valor_deposito_devuelto=data.valorDepositoDevuelto
    o.observacion_deposito=data.observacionDeposito
    db.commit()
    try:
        with httpx.Client(timeout=8) as client:
            client.delete(f"{url('INVENTARIO_URL')}/internal/reservas/{o.id}",headers=internal_headers())
    except httpx.HTTPError:pass
    return serialize(o,db=db)


@app.post('/api/v1/ordenes/{orden_id}/deposito/devolucion')
def reintegrar_deposito(orden_id:int,data:ReintegroDepositoIn,
                       user:dict=Depends(current_user),db:Session=Depends(get_db)):
    """Acta manual: permite completar un depósito retenido al devolver el vehículo."""
    require_role(user,'admin')
    o=locked(db,orden_id)
    if o.estado!='DEVUELTA':raise HTTPException(409,'La orden aún no fue devuelta')
    if o.deposito_devuelto:raise HTTPException(409,'El depósito ya figura devuelto')
    if db.scalar(select(ReporteDano.id).where(ReporteDano.orden_id==orden_id,
                                            ReporteDano.estado=='PENDIENTE').limit(1)):
        raise HTTPException(409,'Revisa primero los daños pendientes')
    o.deposito_devuelto=True
    o.valor_deposito_devuelto=o.deposito_total
    o.observacion_deposito=data.observacion
    db.commit()
    return serialize(o,db=db)


@app.get('/api/v1/danos')
def reportes_danos(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    return [dict(id=d.id,ordenId=d.orden_id,vehiculoId=d.vehiculo_id,
        tipo=d.tipo,severidad=d.severidad,descripcion=d.descripcion,
        costoEstimado=float(d.costo_estimado),estado=d.estado,
        registradoPor=d.registrado_por,observacionAdmin=d.observacion_admin)
        for d in db.scalars(select(ReporteDano).order_by(ReporteDano.id.desc())).all()]


@app.post('/api/v1/danos/{reporte_id}/verificar')
def verificar_dano(reporte_id:int,data:VerificarDanoIn,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    d=db.scalar(select(ReporteDano).where(ReporteDano.id==reporte_id).with_for_update())
    if not d:raise HTTPException(404,'Reporte de daños inexistente')
    if d.estado!='PENDIENTE':raise HTTPException(409,'El reporte ya fue verificado')
    o=locked(db,d.orden_id)
    if data.aprobado:
        try:
            with httpx.Client(timeout=12) as client:
                resp=client.post(f"{url('MULTAS_URL')}/internal/multas",
                    headers=internal_headers(),json={
                        'ordenId':o.id,'usuarioId':o.usuario_id,'tipo':'DANOS',
                        'valorAlquiler':float(o.alquiler_total),
                        'observacion':f'Verificación administrativa, vehículo #{d.vehiculo_id}: {d.descripcion}'})
                if resp.status_code!=409:resp.raise_for_status()
        except (httpx.HTTPError, KeyError):
            db.rollback();raise HTTPException(503,'No se pudo generar la multa validada') from None
    d.estado='VERIFICADO' if data.aprobado else 'RECHAZADO'
    d.verificado_por=user['id'];d.verificado_en=datetime.now(timezone.utc)
    d.observacion_admin=data.observacion
    db.commit()
    return {'id':d.id,'estado':d.estado,'verificadoPor':user['id']}

@app.post('/api/v1/ordenes/{orden_id}/bloquear-cliente')
def bloquear_por_incumplimiento(orden_id:int,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    """Vendedor/admin: únicamente tras devolución tardía o con daños documentados."""
    require_role(user,'vendedor','admin')
    o=locked(db,orden_id)
    fecha_limite=max((x.fecha_fin for x in o.detalles), default=date.today())
    tarde=o.devuelta_en is not None and o.devuelta_en.date()>fecha_limite
    if o.estado!='DEVUELTA' or not (o.reporta_danos or tarde):
        raise HTTPException(409,'Solo es posible bloquear tras una devolución tardía o con daños')
    try:
        with httpx.Client(timeout=8) as client:
            resp=client.post(f"{url('USUARIOS_URL')}/internal/usuarios/{o.usuario_id}/bloquear",
                  headers=internal_headers())
            resp.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503,'No se pudo actualizar el estado del usuario') from None
    return {'usuarioId':o.usuario_id,'activo':False,'ordenId':o.id}
