# ApexSim — Guia de Integração: M2 Esqueleto Ambulante

> Roteiro técnico para a **Semana 6**. Todos param as trilhas individuais e focam nisto.
> **Objetivo:** corrida burra (sem física, sem eventos) rodando de ponta a ponta — `POST /api/races` → motor emitindo voltas por WebSocket → Timing Tower renderizando ao vivo.
> Contratos de dados referenciados aqui estão em [arquitetura.md](arquitetura.md).

---

## 1. Pré-condições: PRs do M1 mergeados na `develop`

- [x] Motor com `tick()`, `RaceState` e seed — **Gabriel (mergeado)**
- [x] Geometria dos circuitos (`circuits/*.json`) — **Octávio (mergeado)**
- [ ] Banco modelado e migrations — **Octávio (PR pendente)**
- [ ] `TrackMap` e `track_maps/*.json` — **Daniel (PR pendente)**
- [ ] Scaffold React + Vite — **Anderson (PR pendente)**

---

## 2. Passo a Passo (ordem importa)

### Passo 1 — Gabriel: criar `backend/sim/engine.py`

O `run.py` existente é só uma CLI. O M2 exige uma **classe controlável** pelo WebSocket:

```python
# backend/sim/engine.py
import asyncio
import random
from .state import RaceState, tick

class RaceEngine:
    def __init__(self, state: RaceState, seed: int):
        self.state = state
        self.rng = random.Random(seed)  # NUNCA usar random global
        self._paused = False
        self._speed = 1.0

    async def run(self, broadcast_fn):
        """Loop principal. Chama tick() e faz broadcast a cada volta."""
        while not self.state.is_finished:
            if self._paused:
                await asyncio.sleep(0.1)
                continue
            self.state = tick(self.state, delta_time=1.0)
            await broadcast_fn(self.state)
            await asyncio.sleep(2.0 / self._speed)  # 1x ≈ 2s por volta

    def pause(self):                      self._paused = True
    def resume(self):                     self._paused = False
    def set_speed(self, x: float):        self._speed = x
```

> **Atenção:** remover os `print()` de debug de `state.py` antes de conectar ao WebSocket.

---

### Passo 2 — Gabriel + Octávio: handler WebSocket no FastAPI

Novo arquivo `backend/app/websocket/races.py`:

```python
import asyncio, json
from fastapi import WebSocket
from sim.engine import RaceEngine

_engines: dict[str, RaceEngine] = {}  # race_id -> engine em execução

async def ws_race_handler(websocket: WebSocket, race_id: str):
    await websocket.accept()
    engine = _engines.get(race_id)
    if not engine:
        await websocket.close(code=4004)
        return

    async def broadcast(state):
        payload = serializar_lap_update(race_id, state)  # ver Contrato D2 em arquitetura.md
        await websocket.send_text(json.dumps(payload))

    loop_task = asyncio.create_task(engine.run(broadcast))
    try:
        while True:
            msg = await websocket.receive_json()
            if msg["action"] == "pause":      engine.pause()
            if msg["action"] == "resume":     engine.resume()
            if msg["action"] == "set_speed":  engine.set_speed(msg["speed_multiplier"])
    except Exception:
        loop_task.cancel()
```

Registrar em `backend/app/main.py`:

```python
from app.websocket.races import ws_race_handler

@app.websocket("/ws/races/{race_id}")
async def websocket_race(websocket: WebSocket, race_id: str):
    await ws_race_handler(websocket, race_id)
```

---

### Passo 3 — Gabriel + Octávio: endpoint `POST /api/races`

Novo arquivo `backend/app/api/races.py`:

```python
import uuid
from fastapi import APIRouter
from sim.run import montar_grid_inicial
from sim.engine import RaceEngine
from app.websocket.races import _engines

router = APIRouter()

@router.post("/api/races")
def criar_corrida(circuito: str, seed: int = 42, laps: int = 53):
    race_id = str(uuid.uuid4())
    state = montar_grid_inicial()
    state.total_laps = laps
    _engines[race_id] = RaceEngine(state, seed=seed)
    return {"race_id": race_id, "ws_url": f"/ws/races/{race_id}"}
```

Registrar o router no `main.py`:
```python
from app.api import races
app.include_router(races.router, tags=["races"])
```

---

### Passo 4 — Anderson: conectar o frontend ao WebSocket real

```typescript
// src/hooks/useRaceWebSocket.ts
const ws = new WebSocket(`ws://localhost:8000/ws/races/${raceId}`);

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "lap_update") updateTimingTower(msg.drivers);
  if (msg.type === "event_update") appendFeed(msg);
};

const pause    = () => ws.send(JSON.stringify({ action: "pause" }));
const resume   = () => ws.send(JSON.stringify({ action: "resume" }));
const setSpeed = (x: number) => ws.send(JSON.stringify({ action: "set_speed", speed_multiplier: x }));
```

---

## 3. Critérios de Aceite do M2

- [ ] `POST /api/races` retorna `race_id` e `ws_url`
- [ ] Conectar em `/ws/races/{race_id}` inicia o recebimento de `lap_update`
- [ ] A Timing Tower atualiza ao vivo com posições e gaps reais do motor
- [ ] `pause` congela a emissão; `resume` retoma do ponto exato onde parou
- [ ] `set_speed: 5` faz a corrida correr 5× mais rápido
- [ ] Duas execuções com `seed=42` produzem exatamente a mesma sequência de voltas
- [ ] `make up` + `POST /api/races` + abrir o front funciona em máquina limpa sem ajuda
