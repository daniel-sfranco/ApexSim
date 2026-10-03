# ApexSim — Guia de Integração: Marco M2

> Roteiro técnico de execução para a integração do **Marco M2**.
> **Objetivo:** Estabelecer o fluxo completo de ponta a ponta da simulação — criação da corrida via API, avanço de voltas com modelos reais de física e pista no motor em memória, transmissão via WebSocket nativo em Python e renderização ao vivo na Timing Tower do frontend.
> Detalhes dos contratos de dados (D2, D3, D4) estão formalizados em [arquitetura.md](arquitetura.md).

---

## 1. Contexto pós-M1: Integração Real (Sem "Corrida Burra")

Com as entregas do Marco M1 já validadas, o M2 integra diretamente os módulos reais de domínio:
* **Física Calibrada (`physics.py`):** Modelo matemático de pneus com curvas reais do Kaggle (Soft, Medium, Hard), cliff logístico, penalidade térmica e consumo de combustível.
* **Pistas Semânticas (`track.py`):** Geometrias e anotações homologadas dos 3 circuitos oficiais (Interlagos, Monza, Mônaco).
* **Persistência (`db/`):** Modelos relacionais e seed do grid 2024.
* **Frontend:** Cockpit e Timing Tower prontos para consumo de telemetria.

O foco exclusivo do M2 é **conectar esses blocos existentes em um fluxo contínuo**.

---

## 2. Roteiro de Integração por Módulo

### Passo 1 — Núcleo de Domínio (`backend/sim/`)

O módulo `sim` deve permanecer **100% puro** (sem I/O, sem dependência de banco de dados ou frameworks web).

* **1.1 Migrar a Física:**
  - Mover `notebooks/fisica-e-eventos/physics.py` para `backend/sim/physics.py`.
* **1.2 Integrar Física e Pista ao Avanço de Estado (`sim/state.py`):**
  - No avanço de cada volta (`tick`), calcular o tempo de volta combinando o tempo-base do circuito, a perda de aderência (`tyre_age` via `physics.py`), a redução de peso de combustível (`fuel_kg`) e a variação estocástica determinística (`rng.gauss`).
  - O comprimento da volta e os limites espaciais devem ser orientados pelas informações do `TrackMap`.

---

### Passo 2 — Orquestrador do Motor (`backend/sim/engine.py`)

Criar a classe `RaceEngine` em `backend/sim/engine.py` para controlar o ciclo de vida da simulação em memória:

* **Responsabilidades:**
  - Gerenciar o loop assíncrono de avanço de tempo (`asyncio.sleep` modulado pela velocidade).
  - Garantir determinismo injetando `random.Random(seed)` no estado.
  - Expor métodos de controle em tempo real: `pause()`, `resume()`, `set_speed(multiplier)` e `stop()`.
  - Disparar um callback assíncrono (`broadcast_fn`) a cada volta concluída com o snapshot do `RaceState`.

---

### Passo 3 — Transporte Web & WebSocket (`backend/app/`)

A camada web deve atuar apenas como ponte de transporte e orquestração entre cliente e motor:

* **3.1 Handler WebSocket em Python (`app/websocket/races.py`):**
  - Conexão em `/ws/races/{race_id}`.
  - Ao iniciar, conecta ao `RaceEngine` associado e envia periodicamente o envelope `lap_update` (especificado no Contrato D2).
  - Recebe comandos do cliente em tempo real (`pause`, `resume`, `set_speed`) e repassa para o engine correspondente.
  - Descontinua e remove o script temporário em Node (`backend/websocket/server.js`).

* **3.2 Endpoint de Criação de Corrida (`app/api/races.py`):**
  - `POST /api/races`: Recebe `circuit_id`, `seed` e `total_laps`.
  - Valida a existência do circuito chamando `TrackMap.load(circuit_id)`.
  - Instancia o `RaceEngine` em memória, registra na tabela de corridas ativas e retorna o `race_id` com a URL do WebSocket.

---

### Passo 4 — Conexão do Frontend (`frontend/src/`)

* No hook `useRaceWebSocket.ts`, apontar a conexão para o endpoint oficial do FastAPI (`ws://localhost:8000/ws/races/${raceId}`).
* Validar que as ações da interface (botões de Play/Pause, controles de velocidade) enviam as mensagens correspondentes pelo socket.
* Confirmar que a Timing Tower e o Minimapa renderizam as posições, compostos e tempos vindos da simulação real.

---

### Passo 5 — Centralização de Testes & Limpeza

* Centralizar os testes da simulação (`test_physics.py`, `test_state.py`, `test_run.py`) dentro de `backend/tests/sim/`.
* Excluir resquícios de arquivos temporários de mock.
* Garantir execução 100% verde da suíte:
  ```bash
  make test && make validate-tracks && make lint
  ```

---

## 3. Critérios de Aceite do Marco M2

- [ ] `POST /api/races` instancia uma corrida a partir de um circuito homologado (Interlagos, Monza ou Mônaco).
- [ ] Conectar ao `/ws/races/{race_id}` transmite snapshots contínuos de `lap_update`.
- [ ] Os tempos de volta refletem a curva de degradação real calculada pelo `physics.py`.
- [ ] A massa de combustível decresce volta a volta e influencia o tempo final de cada volta.
- [ ] Os controles de `pause`, `resume` e `set_speed` (1x, 2x, 5x, 10x) atuam imediatamente no motor.
- [ ] Duas execuções com a mesma `seed` produzem exatamente os mesmos resultados volta a volta.
- [ ] A interface web consome diretamente o backend Python, sem intermediários.
- [ ] Todos os testes unitários e de integração passam via `make test`.

