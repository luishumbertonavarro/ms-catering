"""Pruebas unitarias de los Value Objects del dominio.

Los VO son `dataclass(frozen=True)`. `DireccionEntrega` valida su invariante en
`__post_init__` y lanza `ValueError`; `AnticipacionMinima` encapsula la regla de
los 2 días (HU-28). Al ser objetos puros, se prueban directamente: no hay
dependencias que doblar.
"""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from catering.domain.model.value_objects import (
    AnticipacionMinima,
    DiaSinEntrega,
    DireccionEntrega,
    Etiqueta,
)


# ---------------------------------------------------------------------------
# DireccionEntrega
# ---------------------------------------------------------------------------

class TestDireccionEntrega:

    def test_crear_con_todos_los_campos_los_conserva(self):
        # Arrange / Act
        direccion = DireccionEntrega(
            direccion="Av. Banzer 123",
            referencia="Portón verde",
            zona="Equipetrol",
            latitud=Decimal("-17.7833"),
            longitud=Decimal("-63.1821"),
        )

        # Assert
        assert direccion.direccion == "Av. Banzer 123"
        assert direccion.referencia == "Portón verde"
        assert direccion.zona == "Equipetrol"
        assert direccion.latitud == Decimal("-17.7833")
        assert direccion.longitud == Decimal("-63.1821")

    def test_crear_solo_con_la_direccion_deja_los_opcionales_en_none(self):
        # Arrange / Act
        direccion = DireccionEntrega(direccion="Av. Banzer 123")

        # Assert
        assert direccion.referencia is None
        assert direccion.zona is None
        assert direccion.latitud is None
        assert direccion.longitud is None

    @pytest.mark.parametrize("texto", ["", "   ", "\t\n"])
    def test_crear_con_direccion_vacia_o_en_blanco_lanza_value_error(self, texto):
        # Act / Assert
        with pytest.raises(ValueError, match="no puede estar vacía"):
            DireccionEntrega(direccion=texto)

    def test_modificar_un_campo_de_la_direccion_lanza_error_por_ser_inmutable(self):
        # Arrange
        direccion = DireccionEntrega(direccion="Av. Banzer 123")

        # Act / Assert
        with pytest.raises(FrozenInstanceError):
            direccion.direccion = "Otra"

    def test_dos_direcciones_con_los_mismos_valores_son_iguales(self):
        # Arrange
        una = DireccionEntrega(direccion="Av. Banzer 123", zona="Equipetrol")
        otra = DireccionEntrega(direccion="Av. Banzer 123", zona="Equipetrol")

        # Act / Assert — igualdad por valor, no por identidad
        assert una == otra
        assert hash(una) == hash(otra)

    def test_dos_direcciones_con_distinta_zona_son_distintas(self):
        # Arrange
        una = DireccionEntrega(direccion="Av. Banzer 123", zona="Equipetrol")
        otra = DireccionEntrega(direccion="Av. Banzer 123", zona="Centro")

        # Act / Assert
        assert una != otra


# ---------------------------------------------------------------------------
# AnticipacionMinima — HU-28
# ---------------------------------------------------------------------------

class TestAnticipacionMinima:

    def test_la_anticipacion_minima_exigida_es_de_dos_dias(self):
        # Act / Assert
        assert AnticipacionMinima().DIAS_REQUERIDOS == 2

    @pytest.mark.parametrize(
        ("fecha_solicitud", "esperado"),
        [
            (date(2026, 1, 1), True),    # 9 días antes
            (date(2026, 1, 7), True),    # 3 días antes
            (date(2026, 1, 8), True),    # exactamente 2 días antes: límite permitido
            (date(2026, 1, 9), False),   # 1 día antes
            (date(2026, 1, 10), False),  # el mismo día
            (date(2026, 1, 12), False),  # después de la entrega
        ],
        ids=["9_dias", "3_dias", "2_dias_limite", "1_dia", "mismo_dia", "posterior"],
    )
    def test_es_valida_compara_la_distancia_en_dias_con_el_minimo(
        self, fecha_solicitud, esperado
    ):
        # Arrange
        anticipacion = AnticipacionMinima()
        fecha_entrega = date(2026, 1, 10)

        # Act
        resultado = anticipacion.es_valida(fecha_entrega, fecha_solicitud)

        # Assert
        assert resultado is esperado

    def test_es_valida_cruza_el_cambio_de_mes_sin_errores(self):
        # Arrange — 31 de enero → 2 de febrero son 2 días
        anticipacion = AnticipacionMinima()

        # Act / Assert
        assert anticipacion.es_valida(date(2026, 2, 2), date(2026, 1, 31)) is True

    def test_una_anticipacion_con_otro_minimo_aplica_ese_minimo(self):
        # Arrange — el campo es parametrizable aunque el dominio use siempre 2
        anticipacion = AnticipacionMinima(DIAS_REQUERIDOS=5)

        # Act / Assert
        assert anticipacion.es_valida(date(2026, 1, 10), date(2026, 1, 6)) is False
        assert anticipacion.es_valida(date(2026, 1, 10), date(2026, 1, 5)) is True


# ---------------------------------------------------------------------------
# DiaSinEntrega
# ---------------------------------------------------------------------------

class TestDiaSinEntrega:

    def test_crear_sin_motivo_deja_el_motivo_en_none(self):
        # Arrange / Act
        dia = DiaSinEntrega(fecha=date(2026, 1, 5))

        # Assert
        assert dia.fecha == date(2026, 1, 5)
        assert dia.motivo is None

    def test_dos_dias_con_la_misma_fecha_y_motivo_son_iguales(self):
        # Act / Assert
        assert DiaSinEntrega(date(2026, 1, 5), "Viaje") == DiaSinEntrega(date(2026, 1, 5), "Viaje")

    def test_modificar_el_motivo_lanza_error_por_ser_inmutable(self):
        # Arrange
        dia = DiaSinEntrega(fecha=date(2026, 1, 5), motivo="Viaje")

        # Act / Assert
        with pytest.raises(FrozenInstanceError):
            dia.motivo = "Otro"


# ---------------------------------------------------------------------------
# Etiqueta
# ---------------------------------------------------------------------------

class TestEtiqueta:

    def test_crear_una_etiqueta_conserva_los_datos_del_paquete(self):
        # Arrange / Act
        etiqueta = Etiqueta(
            nombre_paciente="María Pérez",
            codigo_paciente="PAC-0001",
            direccion_entrega="Av. Banzer 123",
            fecha_entrega=date(2026, 1, 5),
            numero_identificacion="1234567",
        )

        # Assert
        assert etiqueta.nombre_paciente == "María Pérez"
        assert etiqueta.codigo_paciente == "PAC-0001"
        assert etiqueta.direccion_entrega == "Av. Banzer 123"
        assert etiqueta.fecha_entrega == date(2026, 1, 5)
        assert etiqueta.numero_identificacion == "1234567"

    def test_modificar_una_etiqueta_lanza_error_por_ser_inmutable(self):
        # Arrange
        etiqueta = Etiqueta("María", "PAC-1", "Av. 1", date(2026, 1, 5), "123")

        # Act / Assert
        with pytest.raises(FrozenInstanceError):
            etiqueta.nombre_paciente = "Otra"
