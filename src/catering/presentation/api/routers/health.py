from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from catering.infrastructure.persistence.database import get_db_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    """Health check que usa Consul: la instancia está sana si responde y llega a su base de datos."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Base de datos no disponible"
        )
    return {"status": "ok", "servicio": "ms-catering"}
