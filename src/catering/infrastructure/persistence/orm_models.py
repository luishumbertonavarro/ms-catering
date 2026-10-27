import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CalendarioEntregaORM(Base):
    __tablename__ = "calendarios_entrega"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('ACTIVO', 'PAUSADO', 'COMPLETADO', 'CANCELADO')",
            name="ck_calendarios_estado",
        ),
        CheckConstraint("fecha_fin >= fecha_inicio", name="ck_calendarios_fechas"),
        Index("idx_calendarios_paciente_id", "paciente_id"),
        Index("idx_calendarios_estado", "estado"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    plan_nutricional_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # lazy="raise": con AsyncSession una carga perezosa implícita no puede hacer
    # I/O (MissingGreenlet). Así, si algún camino olvida cargar el agregado con
    # sus colecciones, falla en el acto con un error claro en vez de un 500 opaco.
    # Toda lectura del agregado pasa por `_EAGER` (calendario_repository_impl.py).
    entregas: Mapped[list["EntregaORM"]] = relationship(
        "EntregaORM", back_populates="calendario", cascade="all, delete-orphan", lazy="raise"
    )
    direcciones_habituales: Mapped[list["DireccionHabitualORM"]] = relationship(
        "DireccionHabitualORM", back_populates="calendario", cascade="all, delete-orphan", lazy="raise"
    )
    dias_sin_entrega: Mapped[list["DiaSinEntregaORM"]] = relationship(
        "DiaSinEntregaORM", back_populates="calendario", cascade="all, delete-orphan", lazy="raise"
    )


class EntregaORM(Base):
    __tablename__ = "entregas"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('PROGRAMADA', 'SIN_ENTREGA', 'CANCELADA', 'ENTREGADA')",
            name="ck_entregas_estado",
        ),
        Index("idx_entregas_calendario_id", "calendario_id"),
        Index("idx_entregas_fecha", "fecha"),
        Index("idx_entregas_calendario_fecha", "calendario_id", "fecha"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    calendario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calendarios_entrega.id", ondelete="CASCADE"),
        nullable=False,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    direccion: Mapped[str] = mapped_column(String(500), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(500), nullable=True)
    zona: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    plan_nutricional_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    etiqueta_nombre_paciente: Mapped[str | None] = mapped_column(String(200), nullable=True)
    etiqueta_codigo_paciente: Mapped[str | None] = mapped_column(String(50), nullable=True)
    etiqueta_numero_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    calendario: Mapped["CalendarioEntregaORM"] = relationship(
        "CalendarioEntregaORM", back_populates="entregas"
    )


class DireccionHabitualORM(Base):
    __tablename__ = "direcciones_habituales"
    __table_args__ = (
        UniqueConstraint("calendario_id", "nombre", name="uq_direcciones_calendario_nombre"),
        Index("idx_direcciones_calendario_id", "calendario_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    calendario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calendarios_entrega.id", ondelete="CASCADE"),
        nullable=False,
    )
    paciente_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    direccion: Mapped[str] = mapped_column(String(500), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(500), nullable=True)
    zona: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    calendario: Mapped["CalendarioEntregaORM"] = relationship(
        "CalendarioEntregaORM", back_populates="direcciones_habituales"
    )


class DiaSinEntregaORM(Base):
    __tablename__ = "dias_sin_entrega"
    __table_args__ = (
        UniqueConstraint("calendario_id", "fecha", name="uq_dias_sin_entrega_fecha"),
        Index("idx_dias_sin_entrega_calendario_id", "calendario_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    calendario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calendarios_entrega.id", ondelete="CASCADE"),
        nullable=False,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(500), nullable=True)

    calendario: Mapped["CalendarioEntregaORM"] = relationship(
        "CalendarioEntregaORM", back_populates="dias_sin_entrega"
    )


# ---------------------------------------------------------------------------
# Mensajería: Transactional Outbox e inbox de idempotencia
# ---------------------------------------------------------------------------

class OutboxORM(Base):
    """Evento de integración pendiente de publicar. Se inserta en la MISMA transacción que el agregado."""

    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventoProcesadoORM(Base):
    """Inbox: mensajes ya consumidos. Evita aplicar dos veces el mismo evento (entrega at-least-once)."""

    __tablename__ = "eventos_procesados"

    message_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    routing_key: Mapped[str] = mapped_column(String(100), nullable=False)
    procesado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
