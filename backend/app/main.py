"""Ponto de entrada da API do ApexSim."""

from fastapi import FastAPI

from app.api import health

app = FastAPI(
    title="ApexSim API",
    description="Simulador de Fórmula 1 — MC857 Turma A",
    version="0.1.0",
)

app.include_router(health.router, tags=["infra"])
