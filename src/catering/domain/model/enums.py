from enum import Enum


class EstadoCalendario(str, Enum):
    ACTIVO = "ACTIVO"
    PAUSADO = "PAUSADO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"


class EstadoEntrega(str, Enum):
    PROGRAMADA = "PROGRAMADA"
    SIN_ENTREGA = "SIN_ENTREGA"
    CANCELADA = "CANCELADA"
    ENTREGADA = "ENTREGADA"
