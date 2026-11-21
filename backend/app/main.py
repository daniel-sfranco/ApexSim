import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import health, races
from app.config import CIRCUITS_DIR, TRACK_EDITOR_DIR, TRACK_MAPS_DIR
from app.websocket import races as ws_races

app = FastAPI(
    title="ApexSim API",
    description="Simulador de Fórmula 1 — MC857 Turma A",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["infra"])
app.include_router(ws_races.router, tags=["websocket"])
app.include_router(races.router, tags=["races"])


@app.get("/api/circuits")
async def list_circuits():
    """Lista os circuitos disponíveis com metadados básicos."""
    if not CIRCUITS_DIR.exists():
        return []
    circuitos = []
    for f in sorted(CIRCUITS_DIR.glob("*.json")):
        try:
            dados = json.loads(f.read_text(encoding="utf-8"))
            circuitos.append(
                {
                    "circuit_id": dados.get("circuit_id", f.stem),
                    "length_m": dados.get("length_m"),
                    "points_count": len(dados.get("points", [])),
                    "meta": dados.get("meta", {}),
                }
            )
        except Exception:
            continue
    return circuitos


@app.get("/api/circuits/{circuit_id}")
async def get_circuit_geometry(circuit_id: str):
    """Retorna a geometria simplificada do circuito (Contrato D3)."""
    f = CIRCUITS_DIR / f"{circuit_id}.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail="Circuito não encontrado")
    return json.loads(f.read_text(encoding="utf-8"))


@app.post("/api/track-maps/{circuit_id}")
async def save_track_map(circuit_id: str, request: Request):
    """Salva diretamente o mapa semântico anotado (Contrato D4) em track_maps/{circuito}.json."""
    dados = await request.json()
    if dados.get("circuit_id") != circuit_id:
        raise HTTPException(status_code=400, detail="circuit_id no corpo não bate com a rota")

    TRACK_MAPS_DIR.mkdir(parents=True, exist_ok=True)
    destino = TRACK_MAPS_DIR / f"{circuit_id}.json"
    destino.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "saved", "path": f"track_maps/{circuit_id}.json"}


@app.get("/api/track-maps/{circuit_id}")
async def get_track_map(circuit_id: str):
    """Retorna o mapa semântico anotado caso já exista em track_maps/{circuito}.json."""
    destino = TRACK_MAPS_DIR / f"{circuit_id}.json"
    if not destino.exists():
        raise HTTPException(status_code=404, detail="Track map não encontrado em track_maps/")
    return json.loads(destino.read_text(encoding="utf-8"))


if CIRCUITS_DIR.exists():
    app.mount("/circuits", StaticFiles(directory=str(CIRCUITS_DIR)), name="circuits")

if TRACK_EDITOR_DIR.exists():
    app.mount(
        "/admin/track-editor",
        StaticFiles(directory=str(TRACK_EDITOR_DIR), html=True),
        name="track-editor",
    )
