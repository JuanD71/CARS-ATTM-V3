from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Vehiculo(Base):
    __tablename__ = "vehiculos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    placa: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    marca: Mapped[str] = mapped_column(String(45), nullable=False)
    linea: Mapped[str] = mapped_column(String(60), nullable=False)
    modelo: Mapped[int] = mapped_column(Integer, nullable=False)
    categoria: Mapped[str] = mapped_column(String(30), nullable=False)
    combustible: Mapped[str] = mapped_column(String(30), nullable=False)
    transmision: Mapped[str] = mapped_column(String(20), nullable=False)
    puestos: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(25), nullable=False)
    maletas: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_dia: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    imagen_url: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="DISPONIBLE", nullable=False)
    __table_args__ = (CheckConstraint("precio_dia > 0"),CheckConstraint("modelo >= 2000"),)

class Reserva(Base):
    __tablename__ = "reservas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    orden_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vehiculo_id: Mapped[int] = mapped_column(ForeignKey("vehiculos.id"), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__=(UniqueConstraint("orden_id", "vehiculo_id"), CheckConstraint("fecha_fin > fecha_inicio"),)

class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehiculo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    administrador_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    accion: Mapped[str] = mapped_column(String(32), nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column(String(20), nullable=True)
    estado_nuevo: Mapped[str] = mapped_column(String(20), nullable=False)
    observacion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
