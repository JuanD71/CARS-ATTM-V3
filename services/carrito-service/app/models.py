from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Cart(Base):
    __tablename__='carritos'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    usuario_id: Mapped[int]=mapped_column(BigInteger,unique=True,index=True,nullable=False)
    creado_en:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Item(Base):
    __tablename__='items_carrito'
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    carrito_id:Mapped[int]=mapped_column(ForeignKey('carritos.id',ondelete='CASCADE'),nullable=False,index=True)
    vehiculo_id:Mapped[int]=mapped_column(Integer,nullable=False)
    marca:Mapped[str]=mapped_column(String(50),nullable=False)
    linea:Mapped[str]=mapped_column(String(60),nullable=False)
    precio_dia:Mapped[Decimal]=mapped_column(Numeric(12,2),nullable=False)
    imagen_url:Mapped[str|None]=mapped_column(String(250),nullable=True)
    fecha_inicio:Mapped[date]=mapped_column(Date,nullable=False)
    fecha_fin:Mapped[date]=mapped_column(Date,nullable=False)
    __table_args__=(UniqueConstraint('carrito_id','vehiculo_id'),CheckConstraint('fecha_fin > fecha_inicio'),)
