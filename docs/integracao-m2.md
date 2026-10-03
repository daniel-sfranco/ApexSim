# ApexSim — Guia de Integração: M2 Integração Real de Ponta a Ponta

> Roteiro técnico para a **Semana 6**. Foco exclusivo na integração dos módulos consolidados no Marco M1.
> **Objetivo:** Uma corrida completa rodando de ponta a ponta — `POST /api/races` cria a corrida com circuito e seed reais → `RaceEngine` em memória executa voltas calculadas com o modelo físico real de degradação (`physics.py`) e limites do circuito (`track.py`) → streaming via WebSocket em Python → Timing Tower do frontend renderizando ao vivo com desgaste real dos pneus.
> Contratos de dados e arquitetura referenciados em [arquitetura.md](arquitetura.md).

---

## 1. Contexto pós-M1: Por que NÃO fazer uma "corrida burra"?

O plano inicial concebeu o M2 como uma "corrida burra" fictícia porque previa que os módulos de física e pistas ainda não existiriam. **A realidade hoje é muito melhor:**
1. **Física Calibrada Pronta (`physics.py`):** Já temos o modelo de pneus calibrado com dados do Kaggle (`TYRE_TABLE` para Soft, Medium, Hard), cliff logístico, penalidade térmica e delta de combustível.
2. **Pistas Oficiais D4 Prontas (`track.py`):** Interlagos, Monza e Mônaco já estão anotados com extensões oficiais, setores, zonas de DRS e limites do pit lane.
3. **Frontend Pronto:** A Timing Tower e o Cockpit já possuem os componentes visuais esperando pneus, voltas e tempos.

Construir mocks ou números aleatórios sem sentido no M2 seria retrabalho descartável. **O M2 integra o domínio real imediatamente.**

---

## 2. Passo a Passo da Integração (Ordem de Execução)

### Passo 1 — Consolidar o Domínio no Módulo `sim/`

#### 1.1 Mover `physics.py` para o motor
Mover `notebooks/fisica-e-eventos/physics.py` para `backend/sim/physics.py`.
O motor passa a ter acesso direto às funções puras:
- `tyre_time_loss(compound, age_laps, track_temp)` (ou consulta direta a `TYRE_TABLE` + `_cliff_term`)
- `fuel_time_delta(fuel_kg)`

#### 1.2 Mover `track.py` para o domínio de simulação
Garantir `TrackMap` e `Zone` em `backend/sim/track.py` (ou `backend/app/models/track.py`), permitindo que a simulação saiba o comprimento exato da pista (`track.length_m`) e as zonas ativas.

#### 1.3 Conectar a Física ao avanço de voltas em `backend/sim/state.py`
No `tick()` ou no avanço de volta:
```python
# Exemplo de calculo no avanco da volta de cada piloto:
pneu_delta = calcular_perda_pneu(driver.tyre_compound, driver.tyre_age)
combustivel_delta = fuel_time_delta(driver.fuel_kg)
ruido_piloto = rng.gauss(0, 0.15)  # variacao estocastica deterministica

driver.last_lap_time = tempo_base_circuito + pneu_delta + combustivel_delta + ruido_piloto
driver.tyre_age += 1
driver.fuel_kg -= consumo_por_volta  # ex: ~1.6 kg/volta
```

---

### Passo 2 — Criar o Orquestrador em Memória (`backend/sim/engine.py`)

O `sim/run.py` existente é apenas um script CLI síncrono. O M2 exige a classe `RaceEngine` assíncrona e controlável:

```python
# backend/sim/engine.py
from __future__ import annotations

import asyncio
import random
from typing import Callable, Awaitable
from sim.state import RaceState, tick
from sim.track import TrackMap


class RaceEngine:
    """Orquestrador do ciclo de vida da corrida em memoria."""

    def __init__(self, state: RaceState, track: TrackMap, seed: int):
        self.state = state
        self.track = track
        self.rng = random.Random(seed)  # Determinismo estrito — nunca random global
        self._paused = False
        self._speed = 1.0
        self._is_running = False

    async def run(self, broadcast_fn: Callable[[RaceState], Awaitable[None]]):
        """Loop principal assincrono. Executa voltas e notifica o WebSocket."""
        self._is_running = True
        while not self.state.is_finished and self._is_running:
            if self._paused:
                await asyncio.sleep(0.1)
                continue

            # Avanco de estado com fisica
            self.state = tick(self.state, delta_time=1.0)
            await broadcast_fn(self.state)

            # Velocidade ajustavel (base: 1 volta = 2 segundos simulados em 1x)
            await asyncio.sleep(2.0 / self._speed)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def set_speed(self, multiplier: float):
        self._speed = max(0.5, min(multiplier, 20.0))

    def stop(self):
        self._is_running = False
```

---

### Passo 3 — Criar o Transporte WebSocket e API REST em Python

#### 3.1 Handler WebSocket nativo (`backend/app/websocket/races.py`)
Substitui definitivamente o arquivo legado `backend/websocket/server.js`:

```python
# backend/app/websocket/races.py
from __future__ import annotations

import asyncio
import json
from fastapi import WebSocket, WebSocketDisconnect
from sim.engine import RaceEngine

_engines: dict[str, RaceEngine] = {}


def register_engine(race_id: str, engine: RaceEngine):
    _engines[race_id] = engine


def get_engine(race_id: str) -> RaceEngine | None:
    return _engines.get(race_id)


async def ws_race_handler(websocket: WebSocket, race_id: str):
    await websocket.accept()
    engine = get_engine(race_id)
    if not engine:
        await websocket.close(code=4004, reason="Corrida nao encontrada")
        return

    async def broadcast(state):
        # Monta o envelope lap_update do Contrato D2
        payload = {
            "type": "lap_update",
            "race_id": race_id,
            "current_lap": state.current_lap,
            "total_laps": state.total_laps,
            "track_status": "GREEN",
            "weather": "DRY",
            "drivers": [
                {
                    "driver_id": d.driver_id,
                    "position": d.position,
                    "gap_to_leader": d.gap_to_leader,
                    "gap_to_ahead": d.gap_to_ahead,
                    "last_lap_time": round(d.last_lap_time, 3),
                    "tyre_compound": d.tyre_compound.upper(),
                    "tyre_age": d.tyre_age,
                    "fuel_load_kg": round(d.fuel_kg, 1),
                    "pit_status": d.pit_status,
                    "pit_stops_made": d.pit_stops,
                    "is_retired": d.is_retired,
                    "drs_active": False,
                    "distance_m": d.distance_m,
                }
                for d in state.drivers
            ],
        }
        await websocket.send_text(json.dumps(payload))

    loop_task = asyncio.create_task(engine.run(broadcast))

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "pause":
                engine.pause()
            elif action == "resume":
                engine.resume()
            elif action == "set_speed":
                engine.set_speed(float(data.get("speed_multiplier", 1.0)))
    except (WebSocketDisconnect, Exception):
        loop_task.cancel()
```

#### 3.2 Endpoint de Criação de Corrida (`backend/app/api/races.py`)
```python
# backend/app/api/races.py
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sim.engine import RaceEngine
from sim.run import montar_grid_inicial
from sim.track import TrackMap
from app.websocket.races import register_engine

router = APIRouter()


class CreateRaceRequest(BaseModel):
    circuit_id: str = "interlagos"
    seed: int = 42
    total_laps: int = 53


@router.post("/api/races")
def criar_corrida(req: CreateRaceRequest):
    try:
        track = TrackMap.load(req.circuit_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Circuito '{req.circuit_id}' invalido.")

    race_id = str(uuid.uuid4())
    state = montar_grid_inicial()
    state.total_laps = req.total_laps

    engine = RaceEngine(state=state, track=track, seed=req.seed)
    register_engine(race_id, engine)

    return {
        "race_id": race_id,
        "circuit_id": track.circuit_id,
        "track_length_m": track.length_m,
        "total_laps": req.total_laps,
        "ws_url": f"/ws/races/{race_id}",
    }
```

Registrar o router e o websocket em `backend/app/main.py`:
```python
from app.api import races
from app.websocket.races import ws_race_handler

app.include_router(races.router, tags=["races"])

@app.websocket("/ws/races/{race_id}")
async def websocket_endpoint(websocket: WebSocket, race_id: str):
    await ws_race_handler(websocket, race_id)
```

---

### Passo 4 — Conectar o Frontend ao WebSocket Real

No arquivo `frontend/src/hooks/useRaceWebSocket.ts`:
- Apontar a conexão WebSocket para `ws://localhost:8000/ws/races/${raceId}`.
- O mock server em Node deixa de ser necessário para a execução integrada.
- As mensagens de `pause`, `resume` e `set_speed` passam a controlar diretamente o `RaceEngine` em Python.

---

### Passo 5 — Limpeza de Legados e Testes Centralizados

1. **Remover o mock Node:** Deletar `backend/websocket/server.js`.
2. **Centralizar testes de simulação:** Mover `test_run.py`, `test_state.py` e `test_physics.py` para `backend/tests/sim/`.
3. **Verificação final:** Executar `make test` e `make lint` para garantir 100% de sucesso contínuo.

---

## 3. Critérios de Aceite do Marco M2 Consolidado

- [ ] `POST /api/races` cria a corrida com circuito homologado (Interlagos, Monza ou Mônaco).
- [ ] Conectar em `/ws/races/{race_id}` inicia a transmissão síncrona de snapshots `lap_update`.
- [ ] Os tempos de volta refletem o modelo físico real de degradação dos pneus de `physics.py` (ex.: tempos do pneu Soft piorando sensivelmente após 15–18 voltas).
- [ ] A massa de combustível decresce a cada volta (`fuel_load_kg`) e alivia o tempo de volta.
- [ ] Comandos `pause`, `resume` e `set_speed` (1x, 2x, 5x) controlam o motor em tempo real.
- [ ] Duas corridas com `seed=42` produzem tempos e ordens de chegada idênticos (determinismo estrito).
- [ ] A Timing Tower no frontend atualiza sem dependência de scripts mock em Node.
- [ ] `make test` e `make validate-tracks` passam com 100% de sucesso.

