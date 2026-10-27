"""Seguridad de endpoints: valida el JWT emitido por el api-gateway y el rol del usuario.

El gateway firma el token (HS256) con el secreto compartido y pone el rol en el claim `rol`.
Validarlo también aquí evita que alguien se salte el gateway llamando directo al puerto del servicio.
"""
from collections.abc import Callable, Iterable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from catering.infrastructure.config import settings

_bearer = HTTPBearer(auto_error=False)
_METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}


def _no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


def validar_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise _no_autorizado("El token expiró")
    except jwt.InvalidTokenError:
        raise _no_autorizado("Token inválido")


def proteger(lectura: Iterable[str], escritura: Iterable[str]) -> Callable:
    """Dependencia de router: GET admite los roles de `lectura`; POST/PATCH/DELETE, los de `escritura`."""
    roles_lectura, roles_escritura = frozenset(lectura), frozenset(escritura)

    def dependencia(
        request: Request,
        credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> dict | None:
        if not settings.auth_habilitada:
            return None
        if credenciales is None:
            raise _no_autorizado("Falta el header Authorization: Bearer <token>")
        payload = validar_token(credenciales.credentials)
        permitidos = roles_lectura if request.method in _METODOS_LECTURA else roles_escritura
        if payload.get("rol") not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"El rol '{payload.get('rol')}' no puede realizar esta operación",
            )
        return payload

    return dependencia
