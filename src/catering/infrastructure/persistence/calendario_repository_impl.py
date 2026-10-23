from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from catering.domain.model import (
    CalendarioEntrega,
    DiaSinEntrega,
    DireccionEntrega,
    DireccionHabitual,
    Entrega,
    EstadoCalendario,
    EstadoEntrega,
)
from catering.domain.repositories import CalendarioEntregaRepository
from catering.infrastructure.persistence.orm_models import (
    CalendarioEntregaORM,
    DiaSinEntregaORM,
    DireccionHabitualORM,
    EntregaORM,
)


def _direccion_from_orm(row: EntregaORM | DireccionHabitualORM) -> DireccionEntrega:
    return DireccionEntrega(
        direccion=row.direccion,
        referencia=row.referencia,
        zona=row.zona,
        latitud=Decimal(str(row.latitud)) if row.latitud is not None else None,
        longitud=Decimal(str(row.longitud)) if row.longitud is not None else None,
    )


def _entrega_from_orm(row: EntregaORM) -> Entrega:
    return Entrega(
        id=row.id,
        calendario_id=row.calendario_id,
        fecha=row.fecha,
        estado=EstadoEntrega(row.estado),
        direccion=_direccion_from_orm(row),
        plan_nutricional_id=row.plan_nutricional_id,
    )


def _dir_habitual_from_orm(row: DireccionHabitualORM) -> DireccionHabitual:
    return DireccionHabitual(
        id=row.id,
        calendario_id=row.calendario_id,
        paciente_id=row.paciente_id,
        nombre=row.nombre,
        direccion=_direccion_from_orm(row),
        es_principal=row.es_principal,
    )


def _calendario_from_orm(row: CalendarioEntregaORM) -> CalendarioEntrega:
    entregas = [_entrega_from_orm(e) for e in row.entregas]
    dirs_habituales = [_dir_habitual_from_orm(d) for d in row.direcciones_habituales]
    dias_sin = [DiaSinEntrega(fecha=d.fecha, motivo=d.motivo) for d in row.dias_sin_entrega]
    return CalendarioEntrega(
        id=row.id,
        paciente_id=row.paciente_id,
        fecha_inicio=row.fecha_inicio,
        fecha_fin=row.fecha_fin,
        estado=EstadoCalendario(row.estado),
        entregas=entregas,
        direcciones_habituales=dirs_habituales,
        dias_sin_entrega=dias_sin,
        plan_nutricional_id=row.plan_nutricional_id,
    )


def _entrega_to_orm(entrega: Entrega) -> EntregaORM:
    return EntregaORM(
        id=entrega.id,
        calendario_id=entrega.calendario_id,
        fecha=entrega.fecha,
        estado=entrega.estado.value,
        direccion=entrega.direccion.direccion,
        referencia=entrega.direccion.referencia,
        zona=entrega.direccion.zona,
        latitud=float(entrega.direccion.latitud) if entrega.direccion.latitud is not None else None,
        longitud=float(entrega.direccion.longitud) if entrega.direccion.longitud is not None else None,
        plan_nutricional_id=entrega.plan_nutricional_id,
        etiqueta_nombre_paciente=entrega.etiqueta.nombre_paciente if entrega.etiqueta else None,
        etiqueta_codigo_paciente=entrega.etiqueta.codigo_paciente if entrega.etiqueta else None,
        etiqueta_numero_id=entrega.etiqueta.numero_identificacion if entrega.etiqueta else None,
    )


def _dir_habitual_to_orm(d: DireccionHabitual) -> DireccionHabitualORM:
    return DireccionHabitualORM(
        id=d.id,
        calendario_id=d.calendario_id,
        paciente_id=d.paciente_id,
        nombre=d.nombre,
        direccion=d.direccion.direccion,
        referencia=d.direccion.referencia,
        zona=d.direccion.zona,
        latitud=float(d.direccion.latitud) if d.direccion.latitud is not None else None,
        longitud=float(d.direccion.longitud) if d.direccion.longitud is not None else None,
        es_principal=d.es_principal,
    )


# El agregado se lee siempre completo: es la frontera de consistencia del BC5.
# `selectinload` (un SELECT ... IN por colección) en vez de `joinedload`: tres
# JOIN sobre colecciones multiplican filas (entregas × direcciones × días).
_EAGER = [
    selectinload(CalendarioEntregaORM.entregas),
    selectinload(CalendarioEntregaORM.direcciones_habituales),
    selectinload(CalendarioEntregaORM.dias_sin_entrega),
]


class CalendarioEntregaRepositoryImpl(CalendarioEntregaRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def guardar(self, calendario: CalendarioEntrega) -> None:
        # Se recarga la fila con sus colecciones. `session.get()` no basta: la
        # fila que leyó `obtener_por_id` ya se tradujo a dominio y el identity map
        # (de referencias débiles) puede haberla soltado; entonces `get()` vuelve
        # a la base sin colecciones y la sincronización de abajo intentaría una
        # carga perezosa, imposible en asyncio.
        result = await self._session.execute(
            select(CalendarioEntregaORM)
            .where(CalendarioEntregaORM.id == calendario.id)
            .options(*_EAGER)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            orm = CalendarioEntregaORM(
                id=calendario.id,
                paciente_id=calendario.paciente_id,
                fecha_inicio=calendario.fecha_inicio,
                fecha_fin=calendario.fecha_fin,
                estado=calendario.estado.value,
                plan_nutricional_id=calendario.plan_nutricional_id,
            )
            for entrega in calendario.entregas:
                orm.entregas.append(_entrega_to_orm(entrega))
            for d in calendario.direcciones_habituales:
                orm.direcciones_habituales.append(_dir_habitual_to_orm(d))
            for dia in calendario.dias_sin_entrega:
                orm.dias_sin_entrega.append(
                    DiaSinEntregaORM(
                        id=uuid4(),
                        calendario_id=calendario.id,
                        fecha=dia.fecha,
                        motivo=dia.motivo,
                    )
                )
            self._session.add(orm)
        else:
            existing.estado = calendario.estado.value
            existing.plan_nutricional_id = calendario.plan_nutricional_id

            # Sync entregas
            existing_entrega_ids = {e.id for e in existing.entregas}
            domain_entrega_ids = {e.id for e in calendario.entregas}

            for e_orm in list(existing.entregas):
                if e_orm.id not in domain_entrega_ids:
                    await self._session.delete(e_orm)

            for entrega in calendario.entregas:
                e_orm = next((e for e in existing.entregas if e.id == entrega.id), None)
                if e_orm is None:
                    existing.entregas.append(_entrega_to_orm(entrega))
                else:
                    e_orm.estado = entrega.estado.value
                    e_orm.direccion = entrega.direccion.direccion
                    e_orm.referencia = entrega.direccion.referencia
                    e_orm.zona = entrega.direccion.zona
                    e_orm.latitud = float(entrega.direccion.latitud) if entrega.direccion.latitud is not None else None
                    e_orm.longitud = float(entrega.direccion.longitud) if entrega.direccion.longitud is not None else None

            # Sync direcciones habituales
            domain_dir_ids = {d.id for d in calendario.direcciones_habituales}
            for d_orm in list(existing.direcciones_habituales):
                if d_orm.id not in domain_dir_ids:
                    await self._session.delete(d_orm)
            for d in calendario.direcciones_habituales:
                if not any(d_orm.id == d.id for d_orm in existing.direcciones_habituales):
                    existing.direcciones_habituales.append(_dir_habitual_to_orm(d))

            # Sync dias sin entrega
            existing_fechas = {d.fecha for d in existing.dias_sin_entrega}
            for dia in calendario.dias_sin_entrega:
                if dia.fecha not in existing_fechas:
                    existing.dias_sin_entrega.append(
                        DiaSinEntregaORM(
                            id=uuid4(),
                            calendario_id=calendario.id,
                            fecha=dia.fecha,
                            motivo=dia.motivo,
                        )
                    )

    async def obtener_por_id(self, id: UUID) -> CalendarioEntrega | None:
        stmt = (
            select(CalendarioEntregaORM)
            .where(CalendarioEntregaORM.id == id)
            .options(*_EAGER)
        )
        result = await self._session.execute(stmt)
        row = result.unique().scalar_one_or_none()
        return _calendario_from_orm(row) if row else None

    async def obtener_por_paciente(self, paciente_id: UUID) -> CalendarioEntrega | None:
        stmt = (
            select(CalendarioEntregaORM)
            .where(
                CalendarioEntregaORM.paciente_id == paciente_id,
                CalendarioEntregaORM.estado == EstadoCalendario.ACTIVO.value,
            )
            .options(*_EAGER)
        )
        result = await self._session.execute(stmt)
        row = result.unique().scalar_one_or_none()
        return _calendario_from_orm(row) if row else None

    async def listar_con_entregas_en_fecha(self, fecha: date) -> list[CalendarioEntrega]:
        stmt = (
            select(CalendarioEntregaORM)
            .join(CalendarioEntregaORM.entregas)
            .where(
                EntregaORM.fecha == fecha,
                EntregaORM.estado == EstadoEntrega.PROGRAMADA.value,
            )
            .options(*_EAGER)
        )
        result = await self._session.execute(stmt)
        rows = result.unique().scalars().all()
        return [_calendario_from_orm(r) for r in rows]

    async def listar_activos(self) -> list[CalendarioEntrega]:
        stmt = (
            select(CalendarioEntregaORM)
            .where(CalendarioEntregaORM.estado == EstadoCalendario.ACTIVO.value)
            .options(*_EAGER)
        )
        result = await self._session.execute(stmt)
        rows = result.unique().scalars().all()
        return [_calendario_from_orm(r) for r in rows]
