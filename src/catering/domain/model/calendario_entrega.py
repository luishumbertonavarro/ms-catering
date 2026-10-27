from datetime import date, timedelta
from uuid import UUID, uuid4

from catering.domain.exceptions.catering_exceptions import (
    CalendarioInactivoError,
    DireccionHabitualDuplicadaError,
    DireccionHabitualNoEncontradaError,
    EntregaNoEncontradaError,
    EntregaNoModificableError,
    FechaFueraDeRangoError,
    AnticipacionInsuficienteError,
)
from catering.domain.model.direccion_habitual import DireccionHabitual
from catering.domain.model.entrega import Entrega
from catering.domain.model.enums import EstadoCalendario, EstadoEntrega
from catering.domain.model.eventos import (
    CalendarioEntregaCancelado,
    CalendarioEntregaCompletado,
    CalendarioEntregaCreado,
    DiaSinEntregaMarcado,
    DireccionEntregaCambiada,
    EventoDominio,
)
from catering.domain.model.value_objects import AnticipacionMinima, DireccionEntrega, DiaSinEntrega


class CalendarioEntrega:
    def __init__(
        self,
        id: UUID,
        paciente_id: UUID,
        fecha_inicio: date,
        fecha_fin: date,
        estado: EstadoCalendario,
        entregas: list[Entrega],
        direcciones_habituales: list[DireccionHabitual],
        dias_sin_entrega: list[DiaSinEntrega],
        plan_nutricional_id: UUID | None = None,
    ):
        self._id = id
        self._paciente_id = paciente_id
        self._fecha_inicio = fecha_inicio
        self._fecha_fin = fecha_fin
        self._estado = estado
        self._entregas: list[Entrega] = entregas
        self._direcciones_habituales: list[DireccionHabitual] = direcciones_habituales
        self._dias_sin_entrega: list[DiaSinEntrega] = dias_sin_entrega
        self._plan_nutricional_id = plan_nutricional_id
        self._eventos: list[EventoDominio] = []

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def crear(
        cls,
        paciente_id: UUID,
        fecha_inicio: date,
        fecha_fin: date,
        direccion_default: DireccionEntrega,
        plan_nutricional_id: UUID | None = None,
    ) -> "CalendarioEntrega":
        calendario_id = uuid4()
        entregas: list[Entrega] = []
        current = fecha_inicio
        while current <= fecha_fin:
            entregas.append(
                Entrega.crear(
                    calendario_id=calendario_id,
                    fecha=current,
                    direccion=direccion_default,
                    plan_nutricional_id=plan_nutricional_id,
                )
            )
            current += timedelta(days=1)

        instance = cls(
            id=calendario_id,
            paciente_id=paciente_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            estado=EstadoCalendario.ACTIVO,
            entregas=entregas,
            direcciones_habituales=[],
            dias_sin_entrega=[],
            plan_nutricional_id=plan_nutricional_id,
        )
        instance._eventos.append(
            CalendarioEntregaCreado(calendario_id=calendario_id, direccion_entrega=direccion_default)
        )
        return instance

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def paciente_id(self) -> UUID:
        return self._paciente_id

    @property
    def fecha_inicio(self) -> date:
        return self._fecha_inicio

    @property
    def fecha_fin(self) -> date:
        return self._fecha_fin

    @property
    def estado(self) -> EstadoCalendario:
        return self._estado

    @property
    def plan_nutricional_id(self) -> UUID | None:
        return self._plan_nutricional_id

    @property
    def entregas(self) -> list[Entrega]:
        return list(self._entregas)

    @property
    def direcciones_habituales(self) -> list[DireccionHabitual]:
        return list(self._direcciones_habituales)

    @property
    def dias_sin_entrega(self) -> list[DiaSinEntrega]:
        return list(self._dias_sin_entrega)

    @property
    def total_dias(self) -> int:
        return len(self._entregas)

    @property
    def eventos(self) -> list[EventoDominio]:
        return list(self._eventos)

    def extraer_eventos(self) -> list[EventoDominio]:
        """Devuelve los eventos pendientes y los vacía: el repositorio los pasa al outbox al guardar."""
        eventos, self._eventos = self._eventos, []
        return eventos

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def cambiar_direccion_entrega(
        self,
        fecha: date,
        nueva_direccion: DireccionEntrega,
        fecha_solicitud: date,
    ) -> None:
        self._verificar_activo()
        self._verificar_rango(fecha)
        self._verificar_anticipacion(fecha, fecha_solicitud)
        entrega = self._obtener_entrega(fecha)
        if not entrega.es_modificable:
            raise EntregaNoModificableError(fecha, entrega.estado.value)
        self._registrar_cambio_direccion(entrega, nueva_direccion, "MANUAL", None)

    def marcar_dia_sin_entrega(
        self,
        fecha: date,
        fecha_solicitud: date,
        motivo: str | None = None,
    ) -> None:
        self._verificar_activo()
        self._verificar_rango(fecha)
        self._verificar_anticipacion(fecha, fecha_solicitud)
        entrega = self._obtener_entrega(fecha)
        if not entrega.es_modificable:
            raise EntregaNoModificableError(fecha, entrega.estado.value)
        entrega.marcar_sin_entrega()
        dia = DiaSinEntrega(fecha=fecha, motivo=motivo)
        self._dias_sin_entrega.append(dia)
        self._eventos.append(
            DiaSinEntregaMarcado(
                calendario_id=self._id, entrega_id=entrega.id, fecha_entrega=fecha, motivo=motivo
            )
        )

    def asignar_direccion_habitual_a_dia(
        self,
        fecha: date,
        nombre_direccion: str,
        fecha_solicitud: date,
    ) -> None:
        self._verificar_activo()
        self._verificar_rango(fecha)
        self._verificar_anticipacion(fecha, fecha_solicitud)
        entrega = self._obtener_entrega(fecha)
        if not entrega.es_modificable:
            raise EntregaNoModificableError(fecha, entrega.estado.value)
        dir_habitual = self._obtener_direccion_habitual(nombre_direccion)
        self._registrar_cambio_direccion(
            entrega, dir_habitual.direccion, "DIRECCION_HABITUAL", nombre_direccion
        )

    def registrar_direccion_habitual(
        self,
        nombre: str,
        direccion: DireccionEntrega,
        es_principal: bool = False,
    ) -> None:
        if any(d.nombre == nombre for d in self._direcciones_habituales):
            raise DireccionHabitualDuplicadaError(nombre)
        nueva = DireccionHabitual.crear(
            calendario_id=self._id,
            paciente_id=self._paciente_id,
            nombre=nombre,
            direccion=direccion,
            es_principal=es_principal,
        )
        self._direcciones_habituales.append(nueva)

    def vincular_plan_nutricional(self, plan_nutricional_id: UUID) -> None:
        """Asocia el plan (evento PlanNutricionalCreado) al calendario y a sus entregas pendientes."""
        self._verificar_activo()
        self._plan_nutricional_id = plan_nutricional_id
        for entrega in self._entregas:
            if entrega.estado == EstadoEntrega.PROGRAMADA:
                entrega.plan_nutricional_id = plan_nutricional_id

    def completar_calendario(self) -> None:
        self._verificar_activo()
        self._estado = EstadoCalendario.COMPLETADO
        self._eventos.append(
            CalendarioEntregaCompletado(
                calendario_id=self._id,
                fecha_fin=self._fecha_fin,
                entregas_realizadas=sum(
                    1 for e in self._entregas if e.estado == EstadoEntrega.ENTREGADA
                ),
                dias_sin_entrega=sum(
                    1 for e in self._entregas if e.estado == EstadoEntrega.SIN_ENTREGA
                ),
            )
        )

    def cancelar_calendario(self) -> None:
        self._verificar_activo()
        self._estado = EstadoCalendario.CANCELADO
        canceladas: list[date] = []
        for entrega in self._entregas:
            if entrega.estado == EstadoEntrega.PROGRAMADA:
                entrega.cancelar()
                canceladas.append(entrega.fecha)
        self._eventos.append(
            CalendarioEntregaCancelado(
                calendario_id=self._id, fechas_canceladas=tuple(sorted(canceladas))
            )
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _registrar_cambio_direccion(
        self,
        entrega: Entrega,
        nueva_direccion: DireccionEntrega,
        origen: str,
        nombre_direccion_habitual: str | None,
    ) -> None:
        anterior = entrega.direccion
        entrega.cambiar_direccion(nueva_direccion)
        self._eventos.append(
            DireccionEntregaCambiada(
                calendario_id=self._id,
                entrega_id=entrega.id,
                fecha_entrega=entrega.fecha,
                origen=origen,
                nombre_direccion_habitual=nombre_direccion_habitual,
                direccion_anterior=anterior,
                direccion_nueva=nueva_direccion,
            )
        )

    def _verificar_activo(self) -> None:
        if self._estado != EstadoCalendario.ACTIVO:
            raise CalendarioInactivoError(self._estado.value)

    def _verificar_rango(self, fecha: date) -> None:
        if not (self._fecha_inicio <= fecha <= self._fecha_fin):
            raise FechaFueraDeRangoError(fecha, self._fecha_inicio, self._fecha_fin)

    def _verificar_anticipacion(self, fecha_entrega: date, fecha_solicitud: date) -> None:
        anticipacion = AnticipacionMinima()
        if not anticipacion.es_valida(fecha_entrega, fecha_solicitud):
            raise AnticipacionInsuficienteError(
                fecha_entrega, fecha_solicitud, anticipacion.DIAS_REQUERIDOS
            )

    def _obtener_entrega(self, fecha: date) -> Entrega:
        for e in self._entregas:
            if e.fecha == fecha:
                return e
        raise EntregaNoEncontradaError(fecha)

    def _obtener_direccion_habitual(self, nombre: str) -> DireccionHabitual:
        for d in self._direcciones_habituales:
            if d.nombre == nombre:
                return d
        raise DireccionHabitualNoEncontradaError(nombre)
