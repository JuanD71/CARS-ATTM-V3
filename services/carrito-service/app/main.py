"""Carrito persistente, máximo 5 vehículos y sin registros predeterminados."""
import os
from contextlib import asynccontextmanager
from datetime import date
from fastapi import Depends,FastAPI,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import httpx
from .db import Base,engine,get_db
from .models import Cart,Item
from .security import current_user,internal_key,require_role

@asynccontextmanager
async def lifespan(app:FastAPI):
    Base.metadata.create_all(engine)
    if engine.dialect.name == 'postgresql':
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE items_carrito ADD COLUMN IF NOT EXISTS imagen_url VARCHAR(250)"))
    yield
app=FastAPI(title='Cars ATTM | Carrito',version='1.0.0',lifespan=lifespan)

class AddItem(BaseModel):
    vehiculoId:int=Field(gt=0)
    fechaInicio:date
    fechaFin:date

def get_or_create(db:Session,user_id:int):
    cart=db.scalar(select(Cart).where(Cart.usuario_id==user_id))
    if not cart:
        cart=Cart(usuario_id=user_id);db.add(cart);db.flush()
    return cart

def result(db:Session,cart:Cart|None):
    if not cart:return {'items':[],'alquiler':0,'deposito':0,'total':0,'cantidad':0}
    items=db.scalars(select(Item).where(Item.carrito_id==cart.id).order_by(Item.id)).all()
    result_items=[]
    for i in items:
        days=(i.fecha_fin-i.fecha_inicio).days
        result_items.append(dict(id=i.id,vehiculoId=i.vehiculo_id,marca=i.marca,linea=i.linea,
           fechaInicio=i.fecha_inicio.isoformat(),fechaFin=i.fecha_fin.isoformat(),dias=days,
           precioDia=float(i.precio_dia),subtotal=float(i.precio_dia*days),
           deposito=float(i.precio_dia*4),imagenUrl=i.imagen_url))
    alquiler=round(sum(x['subtotal'] for x in result_items),2)
    deposito=round(sum(x['deposito'] for x in result_items),2)
    return {'items':result_items,'alquiler':alquiler,'deposito':deposito,
            'total':round(alquiler+deposito,2),'cantidad':len(items)}

@app.get('/health')
def health(db:Session=Depends(get_db)):
    db.execute(text('SELECT 1'));return {'status':'ok'}

@app.get('/api/v1/carrito')
def mostrar(user:dict=Depends(current_user), db:Session=Depends(get_db)):
    cart=db.scalar(select(Cart).where(Cart.usuario_id==user['id']))
    if cart:
        # Refleja tarifas y fotos actuales antes de que el cliente pulse Pagar.
        # Se conserva el precio histórico solo en las órdenes ya confirmadas.
        rows=db.scalars(select(Item).where(Item.carrito_id==cart.id)).all()
        try:
            with httpx.Client(timeout=7) as client:
                for row in rows:
                    r=client.get(f"{os.environ['INVENTARIO_URL'].rstrip('/')}/api/v1/vehiculos/{row.vehiculo_id}")
                    if r.status_code==404:
                        continue  # El checkout dará 409 si el vehículo ya no está disponible.
                    r.raise_for_status()
                    v=r.json()
                    row.precio_dia=v['precioDia']
                    row.imagen_url=v.get('imagenUrl')
            db.commit()
        except (httpx.HTTPError, KeyError, ValueError):
            db.rollback()
            raise HTTPException(503,'No se pudieron actualizar las tarifas del catálogo') from None
    return result(db,cart)

@app.post('/api/v1/carrito/elementos',status_code=201)
def agregar(data:AddItem,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    require_role(user,'cliente')
    if data.fechaInicio < date.today() or data.fechaFin <= data.fechaInicio:
        raise HTTPException(422,'Indica fechas válidas de alquiler')
    # La verificación del inventario se repite al confirmar la orden.
    try:
        with httpx.Client(timeout=7) as client:
            r=client.get(f"{os.environ['INVENTARIO_URL']}/api/v1/vehiculos",
                params={'fechaInicio':data.fechaInicio.isoformat(),'fechaFin':data.fechaFin.isoformat()})
            r.raise_for_status()
            vehicle=next((x for x in r.json() if x['id']==data.vehiculoId),None)
    except (httpx.HTTPError, KeyError, ValueError):
        raise HTTPException(503,'No fue posible consultar disponibilidad') from None
    if vehicle is None:raise HTTPException(409,'Vehículo no disponible para esas fechas')
    # Serialize mutations of a single cart inside PostgreSQL transaction
    cart=get_or_create(db,user['id'])
    db.execute(select(Cart).where(Cart.id==cart.id).with_for_update()).first()
    current=result(db,cart)
    if current['cantidad']>=5: raise HTTPException(409,'El carrito permite hasta cinco vehículos')
    if any(x['vehiculoId']==data.vehiculoId for x in current['items']):
        raise HTTPException(409,'Este vehículo ya está en el carrito')
    db.add(Item(carrito_id=cart.id,vehiculo_id=data.vehiculoId,
        marca=vehicle['marca'],linea=vehicle['linea'],precio_dia=vehicle['precioDia'],imagen_url=vehicle.get('imagenUrl'),
        fecha_inicio=data.fechaInicio,fecha_fin=data.fechaFin))
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'Vehículo duplicado') from None
    return result(db,cart)

@app.delete('/api/v1/carrito/elementos/{item_id}')
def quitar(item_id:int,user:dict=Depends(current_user),db:Session=Depends(get_db)):
    cart=db.scalar(select(Cart).where(Cart.usuario_id==user['id']))
    if not cart:raise HTTPException(404,'Carrito vacío')
    item=db.get(Item,item_id)
    if not item or item.carrito_id!=cart.id:raise HTTPException(404,'Elemento no encontrado')
    db.delete(item);db.commit();return result(db,cart)

@app.delete('/api/v1/carrito')
def vaciar(user:dict=Depends(current_user),db:Session=Depends(get_db)):
    cart=db.scalar(select(Cart).where(Cart.usuario_id==user['id']))
    if cart:
        for item in db.scalars(select(Item).where(Item.carrito_id==cart.id)).all():db.delete(item)
        db.commit()
    return {'items':[],'alquiler':0,'deposito':0,'total':0,'cantidad':0}

@app.delete('/internal/carritos/{usuario_id}',dependencies=[Depends(internal_key)])
def limpiar_compra(usuario_id:int,db:Session=Depends(get_db)):
    cart=db.scalar(select(Cart).where(Cart.usuario_id==usuario_id))
    if cart:
        for item in db.scalars(select(Item).where(Item.carrito_id==cart.id)).all():db.delete(item)
        db.commit()
    return {'limpio':True}
