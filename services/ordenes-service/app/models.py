from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Order(Base):
    __tablename__ = 'ordenes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    estado: Mapped[str] = mapped_column(String(24), default='PAGO_SOLICITADO', nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    alquiler_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deposito_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deposito_recibido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deposito_devuelto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valor_deposito_devuelto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    observacion_deposito: Mapped[str] = mapped_column(Text, default='', nullable=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda:datetime.now(timezone.utc))
    entregada_en: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    devuelta_en: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    observacion_devolucion: Mapped[str|None] = mapped_column(Text, nullable=True)
    reporta_danos: Mapped[bool] = mapped_column(Boolean, default=False)
    detalles: Mapped[list['Detail']] = relationship(back_populates='orden', cascade='all, delete-orphan')
    solicitud_pago: Mapped['PaymentRequest'] = relationship(back_populates='orden', uselist=False, cascade='all, delete-orphan')

class Detail(Base):
    __tablename__ = 'detalle_orden'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey('ordenes.id'), nullable=False, index=True)
    vehiculo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(120), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    precio_dia: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    deposito: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    imagen_url: Mapped[str|None] = mapped_column(String(250), nullable=True)
    orden: Mapped[Order] = relationship(back_populates='detalles')

class PaymentRequest(Base):
    __tablename__ = 'solicitudes_pago'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey('ordenes.id'), unique=True, nullable=False)
    usuario_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14,2), nullable=False)
    modo: Mapped[str] = mapped_column(String(20), default='SIMULADO', nullable=False)
    estado: Mapped[str] = mapped_column(String(24), default='SOLICITADA', nullable=False)
    solicitada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda:datetime.now(timezone.utc))
    revisada_en: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    administrador_id: Mapped[int|None] = mapped_column(BigInteger, nullable=True)
    observacion: Mapped[str] = mapped_column(Text, default='', nullable=False)
    correo_contacto: Mapped[str | None] = mapped_column(String(150), nullable=True)
    telefono_contacto: Mapped[str | None] = mapped_column(String(24), nullable=True)
    documento_contacto: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cuenta_bancaria_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    banco: Mapped[str | None] = mapped_column(String(65), nullable=True)
    cuenta_ultimos4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    orden: Mapped[Order] = relationship(back_populates='solicitud_pago')


class Inspeccion(Base):
    __tablename__ = 'inspecciones_vehiculo'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey('ordenes.id'), nullable=False, index=True)
    vehiculo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(12), nullable=False)  # ENTREGA o DEVOLUCION
    kilometraje: Mapped[int] = mapped_column(Integer, nullable=False)
    nivel_combustible: Mapped[str] = mapped_column(String(16), nullable=False)
    carroceria: Mapped[str] = mapped_column(String(20), nullable=False)
    interior: Mapped[str] = mapped_column(String(20), nullable=False)
    llantas: Mapped[str] = mapped_column(String(20), nullable=False)
    luces: Mapped[str] = mapped_column(String(20), nullable=False)
    observaciones: Mapped[str] = mapped_column(Text, default='', nullable=False)
    responsable_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('orden_id', 'vehiculo_id', 'tipo', name='uq_peritaje_por_fase'),)


class ReporteDano(Base):
    __tablename__ = 'reportes_danos'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey('ordenes.id'), nullable=False, index=True)
    vehiculo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    severidad: Mapped[str] = mapped_column(String(16), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    costo_estimado: Mapped[Decimal] = mapped_column(Numeric(14,2), nullable=False, default=0)
    estado: Mapped[str] = mapped_column(String(16), nullable=False, default='PENDIENTE')
    registrado_por: Mapped[int] = mapped_column(BigInteger, nullable=False)
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    verificado_por: Mapped[int|None] = mapped_column(BigInteger, nullable=True)
    verificado_en: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    observacion_admin: Mapped[str] = mapped_column(Text, default='', nullable=False)
    __table_args__ = (UniqueConstraint('orden_id','vehiculo_id',name='uq_reporte_dano_vehiculo'),)
