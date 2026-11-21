"""Inventario; la reserva es una operación interna atómica en PostgreSQL."""
from contextlib import asynccontextmanager
from pathlib import Path
from io import BytesIO
from uuid import uuid4
import re
import os
from datetime import date
from decimal import Decimal
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .models import Vehiculo, Reserva, MovimientoInventario
from .security import current_user, internal_key, require_role

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    # Migración compatible con bases del ZIP anterior; no elimina datos.
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE vehiculos ADD COLUMN IF NOT EXISTS imagen_url VARCHAR(200) NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE vehiculos ADD COLUMN IF NOT EXISTS estado VARCHAR(20) NOT NULL DEFAULT 'DISPONIBLE'"))
            connection.execute(text("UPDATE vehiculos SET estado='RETIRADO' WHERE activo=FALSE AND estado='DISPONIBLE'"))
            connection.execute(text("UPDATE vehiculos SET imagen_url = '/vehicles/car-' || lpad(((id - 1) % 40 + 1)::text, 2, '0') || '.webp' WHERE imagen_url = '' OR imagen_url IS NULL"))
    yield
app=FastAPI(title="Cars ATTM | Inventario",version="1.0.0",lifespan=lifespan)

class VehiculoIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    placa: str = Field(min_length=5, max_length=8)
    marca: str = Field(min_length=2, max_length=45)
    linea: str = Field(min_length=1, max_length=60)
    modelo: int = Field(ge=2000, le=2100)
    categoria: str
    combustible: str
    transmision: str
    puestos: int = Field(ge=2, le=15)
    color: str
    maletas: int = Field(ge=0,le=10)
    precioDia: Decimal = Field(gt=0)
    descripcion: str = ""
    imagenUrl: str = Field(default="", max_length=200)
    @property
    def imagen_segura(self):
        return bool(re.fullmatch(r'/vehicles/car-[0-9]{2}\.webp|/uploads/vehicles/[0-9a-f]{32}\.webp',self.imagenUrl))

class EstadoIn(BaseModel):
    estado: str
    observacion: str = Field(default="", max_length=500)

class RegistroCambioIn(BaseModel):
    observacion: str = Field(default="", max_length=500)

ESTADOS = {"DISPONIBLE", "MANTENIMIENTO", "RETIRADO"}
IMAGE_DIR=Path(os.getenv('VEHICLE_IMAGES_DIR', '/data/vehicle-images'))
IMAGE_LIMIT=5*1024*1024

@app.post('/api/v1/admin/vehiculos/imagen', status_code=201)
async def subir_imagen(file: UploadFile = File(...), user: dict = Depends(current_user)):
    require_role(user,'admin')
    if file.content_type not in ('image/jpeg','image/png','image/webp'):
        raise HTTPException(422,'Solo se admiten imágenes JPG, PNG o WebP')
    raw=await file.read(IMAGE_LIMIT+1)
    await file.close()
    if len(raw)>IMAGE_LIMIT:
        raise HTTPException(413,'La imagen supera el límite de 5 MB')
    try:
        with Image.open(BytesIO(raw)) as img:
            if img.width*img.height > 16000000:
                raise HTTPException(422,'La fotografía tiene demasiados píxeles')
            img.load()
            if img.format not in ('JPEG','PNG','WEBP'):
                raise HTTPException(422,'El archivo no es una imagen admitida')
            target=img.convert('RGB')
            output=BytesIO()
            target.save(output, format='WEBP', quality=83, method=4)
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(422,'El archivo no contiene una imagen válida') from None
    IMAGE_DIR.mkdir(parents=True,exist_ok=True)
    nombre=f'{uuid4().hex}.webp'
    (IMAGE_DIR/nombre).write_bytes(output.getvalue())
    return {'imagenUrl':f'/uploads/vehicles/{nombre}'}


@app.get('/uploads/vehicles/{nombre}')
def imagen_publica(nombre: str):
    if not re.fullmatch(r'[0-9a-f]{32}\.webp',nombre):
        raise HTTPException(404,'Imagen no encontrada')
    path=IMAGE_DIR/nombre
    if not path.is_file():
        raise HTTPException(404,'Imagen no encontrada')
    return FileResponse(path,media_type='image/webp',headers={'Cache-Control':'public,max-age=86400'})


def registrar(db: Session, vehiculo: Vehiculo, admin_id: int, accion: str,
              anterior: str | None, observacion: str = ""):
    db.add(MovimientoInventario(vehiculo_id=vehiculo.id, administrador_id=admin_id,
                                accion=accion, estado_anterior=anterior,
                                estado_nuevo=vehiculo.estado, observacion=observacion))

def verificar_sin_reservas(db: Session, vehiculo_id: int):
    # No se retira ni mantiene una unidad con reservas vigentes o futuras.
    # Las reservas históricas finalizadas pueden quedar asociadas a la unidad.
    existe = db.scalar(select(Reserva.id).where(
        Reserva.vehiculo_id == vehiculo_id,
        Reserva.activa.is_(True),
        Reserva.fecha_fin > date.today()).limit(1))
    if existe is not None:
        raise HTTPException(409, "El vehículo tiene una orden vigente o futura: resuélvela antes de modificar su disponibilidad")

class ReservaIn(BaseModel):
    ordenId: int = Field(gt=0)
    vehiculoId: int = Field(gt=0)
    fechaInicio: date
    fechaFin: date

def serialize(v: Vehiculo):
    return dict(id=v.id, placa=v.placa, marca=v.marca, linea=v.linea, modelo=v.modelo,
                categoria=v.categoria, combustible=v.combustible, transmision=v.transmision,
                puestos=v.puestos, color=v.color, maletas=v.maletas,
                precioDia=float(v.precio_dia), descripcion=v.descripcion, activo=(v.activo and v.estado=="DISPONIBLE"), estado=v.estado, imagenUrl=v.imagen_url)

def validate_range(start: date | None, end: date | None):
    if (start is None) != (end is None):
        raise HTTPException(422,"Se requieren ambas fechas")
    if start and (start < date.today() or end <= start):
        raise HTTPException(422,"Las fechas deben ser futuras y la devolución posterior al retiro")

def overlapping(db: Session, start:date, end:date):
    return select(Reserva.vehiculo_id).where(Reserva.activa.is_(True),
        Reserva.fecha_inicio < end, Reserva.fecha_fin > start)

@app.get('/health')
def health(db:Session=Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status':'ok'}

@app.get('/api/v1/vehiculos')
def listar(marca:str|None=None,categoria:str|None=None,fechaInicio:date|None=None,
           fechaFin:date|None=None,db:Session=Depends(get_db)):
    validate_range(fechaInicio,fechaFin)
    query=select(Vehiculo).where(Vehiculo.activo.is_(True), Vehiculo.estado=="DISPONIBLE").order_by(Vehiculo.id)
    if marca:query=query.where(Vehiculo.marca.ilike(f'%{marca}%'))
    if categoria:query=query.where(Vehiculo.categoria.ilike(f'%{categoria}%'))
    if fechaInicio:query=query.where(~Vehiculo.id.in_(overlapping(db,fechaInicio,fechaFin)))
    return [serialize(v) for v in db.scalars(query).all()]

@app.get('/api/v1/vehiculos/{vehiculo_id}')
def detalle(vehiculo_id:int, db:Session=Depends(get_db)):
    v=db.get(Vehiculo,vehiculo_id)
    if v is None or not v.activo or v.estado!="DISPONIBLE":raise HTTPException(404,'Vehículo no disponible')
    return serialize(v)

@app.post('/api/v1/vehiculos',status_code=201)
def crear(data:VehiculoIn, user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    if not data.imagen_segura:raise HTTPException(422,'Selecciona o carga una fotografía válida')
    v=Vehiculo(placa=data.placa.upper(),marca=data.marca,linea=data.linea,modelo=data.modelo,
        categoria=data.categoria,combustible=data.combustible,transmision=data.transmision,
        puestos=data.puestos,color=data.color,maletas=data.maletas,precio_dia=data.precioDia,descripcion=data.descripcion,imagen_url=data.imagenUrl,estado="DISPONIBLE")
    db.add(v)
    db.flush();registrar(db,v,user["id"],"ALTA",None,"Vehículo creado por administrador")
    try:db.commit();db.refresh(v)
    except IntegrityError:db.rollback();raise HTTPException(409,'Placa duplicada') from None
    return serialize(v)

@app.get('/api/v1/admin/vehiculos')
def listar_administracion(user:dict=Depends(current_user), db:Session=Depends(get_db)):
    require_role(user,'admin')
    return [serialize(v) for v in db.scalars(select(Vehiculo).order_by(Vehiculo.id.desc())).all()]

@app.get('/api/v1/admin/vehiculos/movimientos')
def movimientos(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    q=select(MovimientoInventario).order_by(MovimientoInventario.id.desc()).limit(150)
    return [dict(id=m.id,vehiculoId=m.vehiculo_id,administradorId=m.administrador_id,
         accion=m.accion,estadoAnterior=m.estado_anterior,estadoNuevo=m.estado_nuevo,
         observacion=m.observacion,registradoEn=m.registrado_en.isoformat())
         for m in db.scalars(q).all()]

@app.put('/api/v1/vehiculos/{vehiculo_id}')
def editar(vehiculo_id:int, data:VehiculoIn, user:dict=Depends(current_user), db:Session=Depends(get_db)):
    require_role(user,'admin')
    if not data.imagen_segura:raise HTTPException(422,'Selecciona o carga una fotografía válida')
    v=db.scalar(select(Vehiculo).where(Vehiculo.id==vehiculo_id).with_for_update())
    if not v:raise HTTPException(404,'Vehículo no encontrado')
    if v.estado=='RETIRADO':raise HTTPException(409,'Reactiva el vehículo antes de editarlo')
    # No editar precio ni identidad si hay alquileres vigentes o futuros:
    # así no se cambia silenciosamente una contratación ya generada.
    if v.placa != data.placa.upper() or v.precio_dia != data.precioDia:
        verificar_sin_reservas(db,vehiculo_id)
    for key,value in {'placa':data.placa.upper(),'marca':data.marca,'linea':data.linea,
        'modelo':data.modelo,'categoria':data.categoria,'combustible':data.combustible,
        'transmision':data.transmision,'puestos':data.puestos,'color':data.color,
        'maletas':data.maletas,'precio_dia':data.precioDia,
        'descripcion':data.descripcion,'imagen_url':data.imagenUrl}.items():
        setattr(v,key,value)
    registrar(db,v,user['id'],'EDICION',v.estado,'Actualización de ficha de vehículo')
    try:db.commit();db.refresh(v)
    except IntegrityError:db.rollback();raise HTTPException(409,'Placa duplicada') from None
    return serialize(v)

@app.patch('/api/v1/vehiculos/{vehiculo_id}/estado')
def cambiar_estado(vehiculo_id:int, data:EstadoIn,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    nuevo=data.estado.upper().strip()
    if nuevo not in ESTADOS:raise HTTPException(422,'Estado inválido. Utiliza DISPONIBLE, MANTENIMIENTO o RETIRADO')
    v=db.scalar(select(Vehiculo).where(Vehiculo.id==vehiculo_id).with_for_update())
    if not v:raise HTTPException(404,'Vehículo no encontrado')
    anterior=v.estado
    if nuevo==anterior:raise HTTPException(409,'El vehículo ya se encuentra en ese estado')
    if nuevo!='DISPONIBLE':verificar_sin_reservas(db,vehiculo_id)
    v.estado=nuevo
    v.activo=(nuevo!='RETIRADO')
    registrar(db,v,user['id'],'ESTADO',anterior,data.observacion)
    db.commit();db.refresh(v)
    return serialize(v)

@app.delete('/api/v1/vehiculos/{vehiculo_id}', status_code=204)
def desactivar(vehiculo_id:int,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'admin')
    v=db.scalar(select(Vehiculo).where(Vehiculo.id==vehiculo_id).with_for_update())
    if not v:raise HTTPException(404,'Vehículo no encontrado')
    if v.estado=='RETIRADO':return
    verificar_sin_reservas(db,vehiculo_id)
    anterior=v.estado;v.estado='RETIRADO';v.activo=False
    registrar(db,v,user['id'],'RETIRO',anterior,'Retirado del catálogo, con historial conservado')
    db.commit()

@app.post('/internal/reservas',status_code=201,dependencies=[Depends(internal_key)])
def reservar(data:ReservaIn,db:Session=Depends(get_db)):
    validate_range(data.fechaInicio,data.fechaFin)
    v=db.scalar(select(Vehiculo).where(Vehiculo.id==data.vehiculoId).with_for_update())
    if not v or not v.activo or v.estado!="DISPONIBLE":raise HTTPException(409,'Vehículo no disponible para nuevas reservas')
    reserva=Reserva(orden_id=data.ordenId,vehiculo_id=data.vehiculoId,
        fecha_inicio=data.fechaInicio,fecha_fin=data.fechaFin)
    db.add(reserva)
    try: db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'El vehículo ya está reservado en estas fechas') from None
    return {'reservado':True,'vehiculoId':v.id,'precioDia':float(v.precio_dia)}

@app.delete('/internal/reservas/{orden_id}',dependencies=[Depends(internal_key)])
def liberar(orden_id:int,db:Session=Depends(get_db)):
    rows=db.scalars(select(Reserva).where(Reserva.orden_id==orden_id,Reserva.activa.is_(True))).all()
    for row in rows: row.activa=False
    db.commit()
    return {'liberadas':len(rows)}
