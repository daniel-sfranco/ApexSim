"""Healthcheck da API — critério de pronto do M0."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Responde 200 enquanto o processo da API estiver de pé."""
    return {"status": "ok"}
