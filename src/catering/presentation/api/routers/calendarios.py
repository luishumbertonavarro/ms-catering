from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from catering.application.commands import (
    AsignarDireccionHabitualADiaCommand,
    CambiarDireccionEntregaCommand,
    CancelarCalendarioCommand,
    CrearCalendarioCommand,
    DireccionData,
    MarcarDiaSinEntregaCommand,
    RegistrarDireccionHabitualCommand,
)
from catering.application.queries import (
    ListarCalendariosActivosQuery,
    ObtenerCalendarioPacienteQuery,
    ObtenerCalendarioPorIdQuery,
    ObtenerEntregasDeFechaQuery,
    VerificarPuedeModificarQuery,
)
from catering.application.use_cases import (
    AsignarDireccionHabitualADiaUseCase,
    CambiarDireccionEntregaUseCase,
    CancelarCalendarioUseCase,
    CrearCalendarioUseCase,
    ListarCalendariosActivosHandler,
    MarcarDiaSinEntregaUseCase,
    ObtenerCalendarioPacienteHandler,
    ObtenerCalendarioPorIdHandler,
    ObtenerEntregasDeFechaHandler,
    RegistrarDireccionHabitualUseCase,
    VerificarPuedeModificarHandler,
)
from catering.domain.repositories import CalendarioEntregaRepository
from catering.domain.services import ValidadorCambioCalendarioService
from catering.infrastructure.persistence import CalendarioEntregaRepositoryImpl, get_db_session
from catering.presentation.api.schemas import (
    AsignarDireccionHabitualRequest,
    CalendarioResponse,
    CambiarDireccionRequest,
    CrearCalendarioRequest,
    DireccionHabitualResponse,
    EntregaResponse,
    MarcarSinEntregaRequest,
    RegistrarDireccionHabitualRequest,
    VerificarModificacionResponse,
    calendario_to_response,
)
from catering.presentation.api.security import proteger

router = APIRouter(prefix="/calendarios", tags=["calendarios"])

# Operaciones de operación/administración: no las hace el paciente.
_solo_admin = [Depends(proteger(lectura=("admin",), escritura=("admin",)))]


async def _get_repo(session: AsyncSession = Depends(get_db_session)) -> CalendarioEntregaRepository:
    return CalendarioEntregaRepositoryImpl(session)


def _get_validador_service() -> ValidadorCambioCalendarioService:
    return ValidadorCambioCalendarioService()


# ── Calendarios ────────────────────────────────────────────────────────────────

@router.post("", response_model=CalendarioResponse, status_code=201, dependencies=_solo_admin)
async def crear_calendario(
    body: CrearCalendarioRequest,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    uc = CrearCalendarioUseCase(repo)
    cmd = CrearCalendarioCommand(
        paciente_id=body.paciente_id,
        fecha_inicio=body.fecha_inicio,
        fecha_fin=body.fecha_fin,
        direccion_inicial=DireccionData(
            direccion=body.direccion_inicial.direccion,
            referencia=body.direccion_inicial.referencia,
            zona=body.direccion_inicial.zona,
        ),
        plan_nutricional_id=body.plan_nutricional_id,
    )
    calendario = await uc.ejecutar(cmd)
    return calendario_to_response(calendario)


@router.get("", response_model=list[CalendarioResponse], dependencies=_solo_admin)
async def listar_calendarios_activos(
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    handler = ListarCalendariosActivosHandler(repo)
    calendarios = await handler.ejecutar(ListarCalendariosActivosQuery())
    return [calendario_to_response(c) for c in calendarios]


@router.get(
    "/entregas/fecha/{fecha}", response_model=list[CalendarioResponse], dependencies=_solo_admin
)
async def obtener_entregas_de_fecha(
    fecha: date,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    handler = ObtenerEntregasDeFechaHandler(repo)
    calendarios = await handler.ejecutar(ObtenerEntregasDeFechaQuery(fecha=fecha))
    return [calendario_to_response(c) for c in calendarios]


@router.get("/verificar-modificacion", response_model=VerificarModificacionResponse)
async def verificar_modificacion(
    fecha_entrega: date,
    fecha_solicitud: date,
    servicio: ValidadorCambioCalendarioService = Depends(_get_validador_service),
):
    handler = VerificarPuedeModificarHandler(servicio)
    result = await handler.ejecutar(
        VerificarPuedeModificarQuery(
            fecha_entrega=fecha_entrega,
            fecha_solicitud=fecha_solicitud,
        )
    )
    return result


@router.get("/paciente/{paciente_id}", response_model=CalendarioResponse)
async def obtener_calendario_paciente(
    paciente_id: UUID,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    handler = ObtenerCalendarioPacienteHandler(repo)
    calendario = await handler.ejecutar(ObtenerCalendarioPacienteQuery(paciente_id=paciente_id))
    if calendario is None:
        raise HTTPException(status_code=404, detail="Calendario no encontrado para el paciente.")
    return calendario_to_response(calendario)


@router.get("/{calendario_id}", response_model=CalendarioResponse)
async def obtener_calendario(
    calendario_id: UUID,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    handler = ObtenerCalendarioPorIdHandler(repo)
    calendario = await handler.ejecutar(ObtenerCalendarioPorIdQuery(calendario_id=calendario_id))
    if calendario is None:
        raise HTTPException(status_code=404, detail="Calendario no encontrado.")
    return calendario_to_response(calendario)


@router.delete("/{calendario_id}", status_code=204, dependencies=_solo_admin)
async def cancelar_calendario(
    calendario_id: UUID,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    uc = CancelarCalendarioUseCase(repo)
    await uc.ejecutar(CancelarCalendarioCommand(calendario_id=calendario_id))


# ── Entregas ───────────────────────────────────────────────────────────────────

@router.get("/{calendario_id}/entregas", response_model=list[EntregaResponse])
async def listar_entregas(
    calendario_id: UUID,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    handler = ObtenerCalendarioPorIdHandler(repo)
    calendario = await handler.ejecutar(ObtenerCalendarioPorIdQuery(calendario_id=calendario_id))
    if calendario is None:
        raise HTTPException(status_code=404, detail="Calendario no encontrado.")
    return [
        EntregaResponse(
            id=e.id,
            fecha=e.fecha,
            estado=e.estado.value,
            direccion=e.direccion.direccion,
            referencia=e.direccion.referencia,
            zona=e.direccion.zona,
            tiene_etiqueta=e.tiene_etiqueta,
        )
        for e in calendario.entregas
    ]


@router.patch("/{calendario_id}/entregas/{fecha}/direccion", status_code=204)
async def cambiar_direccion_entrega(
    calendario_id: UUID,
    fecha: date,
    body: CambiarDireccionRequest,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    uc = CambiarDireccionEntregaUseCase(repo)
    cmd = CambiarDireccionEntregaCommand(
        calendario_id=calendario_id,
        fecha_entrega=fecha,
        nueva_direccion=DireccionData(
            direccion=body.nueva_direccion.direccion,
            referencia=body.nueva_direccion.referencia,
            zona=body.nueva_direccion.zona,
        ),
        fecha_solicitud=date.today(),
    )
    await uc.ejecutar(cmd)


@router.patch("/{calendario_id}/entregas/{fecha}/sin-entrega", status_code=204)
async def marcar_sin_entrega(
    calendario_id: UUID,
    fecha: date,
    body: MarcarSinEntregaRequest,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    uc = MarcarDiaSinEntregaUseCase(repo)
    cmd = MarcarDiaSinEntregaCommand(
        calendario_id=calendario_id,
        fecha=fecha,
        fecha_solicitud=date.today(),
        motivo=body.motivo,
    )
    await uc.ejecutar(cmd)


@router.patch("/{calendario_id}/entregas/{fecha}/direccion-habitual", status_code=204)
async def asignar_direccion_habitual_a_dia(
    calendario_id: UUID,
    fecha: date,
    body: AsignarDireccionHabitualRequest,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    uc = AsignarDireccionHabitualADiaUseCase(repo)
    cmd = AsignarDireccionHabitualADiaCommand(
        calendario_id=calendario_id,
        fecha_entrega=fecha,
        nombre_direccion=body.nombre_direccion,
        fecha_solicitud=date.today(),
    )
    await uc.ejecutar(cmd)


# ── Direcciones habituales ─────────────────────────────────────────────────────

@router.post("/{calendario_id}/direcciones", status_code=204)
async def registrar_direccion_habitual(
    calendario_id: UUID,
    body: RegistrarDireccionHabitualRequest,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    uc = RegistrarDireccionHabitualUseCase(repo)
    cmd = RegistrarDireccionHabitualCommand(
        calendario_id=calendario_id,
        nombre=body.nombre,
        direccion=DireccionData(
            direccion=body.direccion.direccion,
            referencia=body.direccion.referencia,
            zona=body.direccion.zona,
        ),
        es_principal=body.es_principal,
    )
    await uc.ejecutar(cmd)


@router.get("/{calendario_id}/direcciones", response_model=list[DireccionHabitualResponse])
async def listar_direcciones_habituales(
    calendario_id: UUID,
    repo: CalendarioEntregaRepository = Depends(_get_repo),
):
    handler = ObtenerCalendarioPorIdHandler(repo)
    calendario = await handler.ejecutar(ObtenerCalendarioPorIdQuery(calendario_id=calendario_id))
    if calendario is None:
        raise HTTPException(status_code=404, detail="Calendario no encontrado.")
    return [
        DireccionHabitualResponse(
            id=d.id,
            nombre=d.nombre,
            direccion=d.direccion.direccion,
            referencia=d.direccion.referencia,
            zona=d.direccion.zona,
            es_principal=d.es_principal,
        )
        for d in calendario.direcciones_habituales
    ]
