from catering.domain.model import CalendarioEntrega
from catering.presentation.api.schemas.schemas import (
    CalendarioResponse,
    DireccionHabitualResponse,
    EntregaResponse,
)


def calendario_to_response(calendario: CalendarioEntrega) -> CalendarioResponse:
    entregas = [
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
    dirs_habituales = [
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
    return CalendarioResponse(
        id=calendario.id,
        paciente_id=calendario.paciente_id,
        fecha_inicio=calendario.fecha_inicio,
        fecha_fin=calendario.fecha_fin,
        estado=calendario.estado.value,
        total_dias=calendario.total_dias,
        plan_nutricional_id=calendario.plan_nutricional_id,
        entregas=entregas,
        direcciones_habituales=dirs_habituales,
    )
