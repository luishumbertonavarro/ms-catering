"""Dependencia `proteger`: valida el JWT del api-gateway y el rol según el método HTTP.

Se invoca la dependencia directamente con un `Request` construido a mano: no se levanta cliente HTTP.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from catering.infrastructure.config import settings
from catering.presentation.api.security import proteger

dependencia = proteger(
    lectura=("admin", "nutricionista", "paciente"), escritura=("admin", "nutricionista")
)


@pytest.fixture(autouse=True)
def auth_habilitada(monkeypatch):
    monkeypatch.setattr(settings, "auth_habilitada", True)


def _request(metodo: str) -> Request:
    return Request({"type": "http", "method": metodo, "path": "/calendarios", "headers": []})


def _credenciales(secreto: str | None = None, **claims) -> HTTPAuthorizationCredentials:
    payload = {
        "sub": "u",
        "rol": "nutricionista",
        "iss": settings.jwt_issuer,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    } | claims
    token = jwt.encode(payload, secreto or settings.jwt_secret, algorithm="HS256")
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_sin_token_devuelve_401():
    # Act / Assert
    with pytest.raises(HTTPException) as error:
        dependencia(_request("GET"), None)
    assert error.value.status_code == 401


def test_token_valido_con_rol_permitido_devuelve_los_claims():
    # Act
    claims = dependencia(_request("POST"), _credenciales())

    # Assert
    assert claims["rol"] == "nutricionista"


def test_paciente_puede_leer():
    # Act
    claims = dependencia(_request("GET"), _credenciales(rol="paciente"))

    # Assert
    assert claims["rol"] == "paciente"


def test_paciente_no_puede_escribir_devuelve_403():
    # Act / Assert
    with pytest.raises(HTTPException) as error:
        dependencia(_request("POST"), _credenciales(rol="paciente"))
    assert error.value.status_code == 403


def test_token_expirado_devuelve_401():
    # Arrange
    vencido = _credenciales(exp=datetime.now(timezone.utc) - timedelta(minutes=1))

    # Act / Assert
    with pytest.raises(HTTPException) as error:
        dependencia(_request("GET"), vencido)
    assert error.value.status_code == 401
    assert error.value.detail == "El token expiró"


def test_token_de_otro_emisor_devuelve_401():
    # Act / Assert
    with pytest.raises(HTTPException) as error:
        dependencia(_request("GET"), _credenciales(iss="otro-emisor"))
    assert error.value.status_code == 401


def test_token_firmado_con_otro_secreto_devuelve_401():
    # Act / Assert
    with pytest.raises(HTTPException) as error:
        dependencia(_request("GET"), _credenciales(secreto="otro-secreto-de-al-menos-32-bytes!!"))
    assert error.value.status_code == 401
    assert error.value.detail == "Token inválido"


def test_con_auth_deshabilitada_no_exige_token(monkeypatch):
    # Arrange
    monkeypatch.setattr(settings, "auth_habilitada", False)

    # Act / Assert
    assert dependencia(_request("POST"), None) is None
