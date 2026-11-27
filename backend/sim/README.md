# Motor de Simulação (`backend/sim`)

Este diretório contém o **núcleo de domínio** do ApexSim: o estado da corrida, a
física de volta, os eventos estocásticos, as ultrapassagens, a estratégia de pit
stop e o orquestrador `RaceEngine`. O pacote é puro: não conhece FastAPI,
WebSocket, banco de dados nem o frontend. A camada de aplicação (`backend/app`)
consome o motor e é responsável por persistência e transporte.

> Contratos formais: `lap_update` e `event_update` seguem o Contrato D2;
> o mapa de pista segue o Contrato D4. As decisões de pit usam a heurística de
> `backend/strategy`, que **não é alterada** pelo motor — o motor apenas adapta
> os dados e aplica os perfis individuais.

---

## 1. Visão geral do fluxo

```
                         ┌──────────────────────────────┐
                         │        RaceEngine            │
                         │  (orquestra tudo por tick)   │
                         └──────────────┬───────────────┘
                                        │ step_tick()
        ┌───────────────────────────────┼───────────────────────────────┐
        ▼                               ▼                               ▼
┌───────────────┐              ┌─────────────────┐              ┌───────────────┐
│ _advance_     │              │ _evaluate_pit_  │              │ _resolve_     │
│ cooldowns()   │              │ stops()         │              │ overtakes()   │
└───────────────┘              └────────┬────────┘              └───────┬───────┘
                                        │ adapta estado                 │
                                        ▼                               ▼
                              ┌──────────────────┐            ┌──────────────────┐
                              │ strategy.heuristic│            │ sim.overtaking   │
                              └──────────────────┘            └──────────────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │ sim.state.tick() │  física + deslocamento + voltas
                              └────────┬─────────┘
                                       ▼
                     ┌─────────────────────────────────┐
                     │ incidentes (NHPP) + SC/VSC +     │
                     │ clima dinâmico + novos envelopes │
                     └─────────────────────────────────┘
```

Cada `step_tick(delta_time)`:

1. decrementa cooldowns de ultrapassagem;
2. avalia pit stops dos pilotos na janela de entrada;
3. sorteia ultrapassagens;
4. executa `tick()` (física, deslocamento, bloqueio físico, combustível, voltas);
5. sorteia incidentes para quem cruzou a linha;
6. avança direção de prova e clima ao fechar volta do líder;
7. entrega voltas/eventos aos ganchos de persistência.

`step_lap()` repete `step_tick()` até o líder concluir uma volta (limite de 2000
ticks). `run()` é o loop assíncrono de tempo real.

---

## 2. Mapa dos módulos

| Arquivo | Responsabilidade |
|---|---|
| `state.py` | `RaceState`, `DriverState`, `LapResult`, enums (`TyreCompound`, `PitStatus`, `TrackStatus`), `tick()` e `format_lap_update()` (Contrato D2). |
| `physics.py` | Funções puras de degradação de pneu, combustível, ar sujo, DRS e grip. |
| `weather.py` | Cadeia de Markov do clima, penalidades composto × clima e greedy de grip. |
| `events.py` | Incidentes por Processo de Poisson Não-Homogêneo (NHPP) e máquina de estados de Safety Car/VSC. |
| `overtaking.py` | Probabilidade de ultrapassagem por zona e aplicação da troca de posição. |
| `track.py` | `TrackMap` e `Zone` (Contrato D4): setores, frenagens, DRS, pit lane, pontos de ultrapassagem. |
| `strategy_profile.py` | Perfis determinísticos por piloto (ritmo, gestão de pneu, pit crew, agressividade). |
| `engine.py` | `RaceEngine`: ciclo de vida, adaptação para a heurística, eventos, callbacks e loop. |
| `run.py` | Grid inicial, alocação padrão de pneus e um smoke síncrono de física. |
| `realtime_loop.py` | Fachada `run_realtime_loop()` para subir o motor com parâmetros simples. |
| `test_*.py` | Testes unitários e de integração do motor. |

---

## 3. Modelo de dados

### `TyreCompound`

`SOFT`, `MEDIUM`, `HARD`, `INTERMEDIATE`, `WET`, `UNKNOWN`.

### `PitStatus`

`NONE` (em pista), `ENTERING`, `IN_PIT` (parado no box), `EXITING`.

### `TrackStatus`

`GREEN`, `YELLOW` (VSC no Contrato D2), `SAFETY_CAR`, `RED`.

### `DriverState`

Campos principais:

- identidade: `driver_id`, `name`, `team`, `position`;
- posição física: `lap_distance_covered`, `total_distance_covered`, `current_lap`;
- ritmo: `base_velocity` (m/s), `last_lap_time`, `lap_time_sum`;
- pneus: `tyre_compound`, `tyre_age`;
- corrida: `fuel_load`, `pit_status`, `pit_stops_made`, `is_retired`;
- controle: `pit_time_remaining`, `pit_stop_in_this_lap`, `pit_time_in_this_lap`,
  `overtake_cooldown_s`, `incident_time_remaining`, `drs_active`.

### `RaceState`

`current_lap`, `total_laps`, `track_status`, `drivers` (dict por código FIA),
`elapsed_time`, `lap_history`, `cumulative_lap_times`, `is_finished`.

### `LapResult`

Registro imutável de uma volta de um piloto: tempo, posição, gaps, composto,
idade do pneu, combustível, flag de pit e duração do pit.

---

## 4. O `tick()` em detalhe

`tick(state, delta_time, track_length, rng, track_map, track_temp, use_physics, ...)`

### 4.1 Velocidade efetiva

Quando `use_physics=True`:

```
t_base    = track_length / base_velocity
t_tyre    = tyre_time_loss(composto, idade, track_temp)
t_weather = weather_time_delta(composto, clima)
t_fuel    = fuel_time_delta(combustivel)
t_dirty   = dirty_air_time_delta(gap_to_ahead)
drs_gain  = drs_zone_time_gain(zona, elegivel)

t_effective = max(10, (t_base + t_tyre + t_weather + t_fuel + t_dirty - drs_gain) * sc_factor)
v_eff       = track_length / t_effective
```

- `sc_factor = 1.40` sob Safety Car e `1.25` sob VSC.
- No pit lane, `v_eff` é limitado a `pit_speed_limit_ms` da zona `pit_lane`.
- `delta_time` é reduzido pelo tempo restante de pit/incidente.

O deslocamento do tick é `(v_eff + ruído gaussiano) * tempo_movimento`, com
`ruído ~ N(0, 0.4)` m/s, usando o `rng` injetado (determinístico).

### 4.2 Bloqueio físico

Os carros em pista são ordenados por `total_distance_covered` e cada um tem o
passo limitado a `MIN_CAR_GAP_M = 8.0` atrás do rival da frente. Cobrir mais
metros no tick **não** ultrapassa: a ordem só muda em `sample_overtake()`.
Carros no pit e finalizados ficam fora da corrente.

### 4.3 Combustível

Consumo contínuo de `~1.6 kg/volta` proporcional à distância percorrida, com piso
de `2.0 kg`.

### 4.4 Cruzamento de linha e voltas

Ao cruzar a linha:

- se o carro veio do grid (`total_distance_covered < 0`), o primeiro cruzamento
  é a **largada** e apenas inicia a contagem da volta 1;
- caso contrário, calcula `lap_time`, incrementa `current_lap` e `tyre_age`,
  registra `LapResult` e acumula `cumulative_lap_times`.

### 4.5 Classificação e gaps

A classificação usa a maior distância total (ou menor tempo no encerramento).
Os gaps são calculados por diferença de tempos acumulados de volta:

- `gap_to_leader` e `gap_to_ahead` são tempos em segundos;
- na volta 1 (`current_lap == 0`), `format_lap_update()` zera os gaps de exibição
  para não mostrar o stagger do grid como diferença de corrida.

---

## 5. Física (`physics.py`)

Todas as funções são puras e documentadas em `docs/fisica.md`.

### Pneus

```
t_tire(a,c) = k1_quad*a² + k2_lin*a + cliff(a,c) + temp_penalty(T)
cliff(a,c)  = cliff_delta / (1 + exp(-cliff_beta*(a - cliff_age)))
```

Tabela calibrada para `soft`, `medium`, `hard`, `intermediate` e `wet`.
`tyre_grip()` converte a perda de tempo em fator de aderência normalizado.

### Combustível

`fuel_time_delta(m) = 0.03 * m` s (m em kg).

### Ar sujo

`dirty_air_time_delta(g) = 0.42 * exp(-g / 0.65)` para `g <= 3.0 s`; acima disso,
zero. Afeta também o grip aerodinâmico.

### DRS

Elegível com gap `< 1.0 s`, pista seca, bandeira verde e fora da volta de
relargada. O ganho é proporcional à extensão das zonas `drs_activation` do
`TrackMap`.

---

## 6. Estratégia de pit stop

### 6.1 Heurística (`backend/strategy/heuristic.py`)

A decisão segue prioridades:

1. **RED_FLAG** — troca gratuita com pneu usado.
2. **WEATHER** — composto incompatível com a pista.
3. **SAFETY_CAR / VSC** — custo de parada reduzido (SC pleno).
4. **UNDERCUT** — rival imediatamente atrás parou e o gap é pequeno.
5. **DEGRADATION** — perda acumulada projetada supera o custo ajustado pela
   agressividade.

Agressividade base por equipe em `strategy/config.py`. O motor **não altera** a
heurística: ele passa `pit_lane_loss_s` e `degradation_curve` já ajustados por
piloto.

### 6.2 Janela espacial de pit

A avaliação ocorre apenas quando o piloto está nos **últimos 15%** ou nos
**primeiros 5%** do traçado, a partir da volta 2. A parada é aplicada no tick
seguinte, com `PitStatus.IN_PIT`.

### 6.3 Perfis individuais (`strategy_profile.py`)

Para evitar que todos os pilotos decidam parar na mesma volta, cada piloto
recebe um perfil determinístico derivado de `CRC32(seed, driver_id)`:

| Desvio | Constante | Efeito |
|---|---|---|
| `pace_offset_ms` | `PACE_SPREAD_MS = 0.5` m/s | cria gaps reais ao longo da corrida. |
| `tyre_factor` | `TYRE_MANAGEMENT_SPREAD = 0.10` | desloca o limiar de degradação em 1–3 voltas. |
| `pit_crew_delta_s` | `PIT_CREW_SPREAD_S = 0.8` s | altera o custo esperado e a duração real da parada. |
| `aggression_jitter` | `AGGRESSION_JITTER = 0.10` | soma à agressividade base da equipe. |

Além disso, cada parada recebe um ruído de `PIT_STOP_NOISE_S = 0.3 s`. A mesma
seed produz exatamente os mesmos perfis — a corrida continua reproduzível.

### 6.4 Gate de undercut no motor

O pelotão costuma andar colado, então a regra de undercut da heurística podia
fazer o carro à frente reagir, depois o próximo, e assim por diante. O motor
aplica um gate em `_undercut_allowed()`:

- o gap físico para o rival atrás precisa estar entre `0.5 s` e `1.8 s`
  (`UNDERCUT_MIN_GAP_S` / `UNDERCUT_GAP_THRESHOLD_S`);
- o rival precisa ter **concluído** a parada na volta anterior
  (`UNDERCUT_REACTION_WINDOW_LAPS = 1`), e não estar no box agora;
- cada piloto reage no máximo **uma vez por stint** (controlado por
  `_undercut_reaction_age`).

Se o gate rejeitar, a parada daquele tick é ignorada; a degradação ainda pode
disparar na volta seguinte. Isso quebra a reação em cadeia sem alterar a
heurística.

> Sob Safety Car pleno, o pelotão inteiro pode parar na mesma volta — isso é
> intencional e realista (parada barata). O gate vale para bandeira verde.

### 6.5 Alocação inicial de pneus

`montar_grid_inicial()` usa `DEFAULT_TYRE_ALLOCATION` quando o setup não define
o composto do piloto:

| Faixa do grid | Composto |
|---|---|
| P1–P6 | `SOFT` |
| P7–P14 | `MEDIUM` |
| P15–P20 | `HARD` |

Compostos explícitos do setup sempre têm prioridade; valores desconhecidos caem
em `MEDIUM`. Isso faz os stints iniciais serem diferentes e espalha a primeira
janela de paradas.

---

## 7. Eventos estocásticos e direção de prova

### 7.1 Incidentes (`events.py`)

Cada piloto que cruza a linha amostra um NHPP sobre as zonas de frenagem:

```
Lambda_volta = Σ λ_base * w_frenagem * w_grip * w_clima * w_agressão * L_i
P(incidente) = 1 - exp(-Lambda_volta)
```

Consequências possíveis: `TIME_LOSS`, `VSC` ou `SC`, com probabilidade dependente
do runoff da zona. O motor aplica perda de tempo, aposentadoria e emite
`ACCIDENT`/`RETIREMENT`.

### 7.2 Safety Car / VSC (`SafetyCarStateMachine`)

- `SC`: 2–4 voltas, multiplicador de tempo `1.40`, pelotão comprimido em fila
  com `0.5 s` entre carros, DRS bloqueado na relargada.
- `VSC`: 1–2 voltas, multiplicador `1.25`, gaps relativos mantidos.
- `GREEN`: ritmo normal.

Eventos emitidos: `SAFETY_CAR_DEPLOYED`, `VSC_DEPLOYED`, `GREEN_FLAG`.

### 7.3 Clima dinâmico (`weather.py`)

Quando `dynamic_weather=True`, uma Cadeia de Markov evolui `seco → umido →
molhado` a cada volta do líder. A troca de estado emite `WEATHER_CHANGED`.
Penalidades de tempo e grip são aplicadas por composto, produzindo o crossover
de pneus de chuva.

---

## 8. Ultrapassagens (`overtaking.py`)

Só há tentativa em bandeira verde, a partir da volta 2, com gap `<= 0.8 s`, em
uma zona de ultrapassagem. A probabilidade considera:

- delta de ritmo entre atacante e defensor;
- gap no ponto de detecção;
- DRS ativo (peso extra);
- dificuldade da zona.

Cada atacante tenta uma vez por travessia de zona; o cooldown do atacante é
`max(4.0 s, tempo de travessia)` e o do defensor `3.0 s`. A troca de posição é
aplicada no estado e o motor emite `OVERTAKE`.

---

## 9. `TrackMap` (Contrato D4)

`TrackMap.load("interlagos")` carrega o JSON de `track_maps/`. A API oferece:

- `get_zones_at(distance_m)` e `get_active_sector()`;
- `get_braking_zone_at()`, `is_drs_active()`, `get_drs_activation_zone_at()`;
- `get_overtaking_zone_at()`;
- `is_in_pit_lane()`, `get_pit_lane_zone()`;
- `pit_speed_limit_kmh()`, `pit_speed_limit_ms()`, `pit_time_loss_s()`.

Os fallbacks de pit lane são `80 km/h` e `22.0 s` quando o circuito não anota a
zona `pit_lane`.

---

## 10. `RaceEngine`

### 10.1 Construção

```python
engine = RaceEngine(
    race_state=state,  # grid montado por montar_grid_inicial()
    track_length=4309.0,
    race_id="...",
    seed=42,
    weather="DRY",
    track_temp=32.0,
    delta_time=0.5,
    track_map=TrackMap.load("interlagos"),
    dynamic_weather=False,
    broadcast_fn=...,
    on_lap_closed=...,
    on_finished=...,
)
```

No `__init__`, o motor:

- carrega os valores de pit lane do `TrackMap`;
- monta `driver_profiles` e aplica ritmo/agressividade/curvas individuais;
- inicializa `random.Random(seed)`, a máquina de SC e o simulador climático.

### 10.2 Controles

- `play()`, `pause()`, `resume()`, `stop()`;
- `set_speed(multiplier)` (0.25x a 20x);
- `handle_command({"action": "play" | "pause" | "set_speed" | "stop", ...})`.

### 10.3 Callbacks

- `broadcast_fn(envelope)`: recebe `lap_update` e `event_update` (pode ser sync ou
  async);
- `on_lap_closed(voltas, eventos)`: uma vez por volta do líder, com as voltas e
  eventos fechados desde a última entrega (usado para persistir no banco);
- `on_finished()`: uma vez ao terminar a corrida.

### 10.4 Envelopes

`get_lap_update_envelope()` devolve `type`, `race_id`, `current_lap`,
`total_laps`, `track_status`, `weather`, `track_temp` e `drivers[]` com
identidade, posição, gaps, último tempo, composto, idade, combustível, status de
pit, paradas, aposentadoria, DRS e `distance_m`.

Eventos usam `type="event_update"`, `event_type`, `involved_drivers`, `zone_id`,
`description` e `lap`.

Eventos emitidos pelo motor: `PIT_STOP`, `OVERTAKE`, `ACCIDENT`, `RETIREMENT`,
`SAFETY_CAR_DEPLOYED`, `VSC_DEPLOYED`, `GREEN_FLAG`, `WEATHER_CHANGED`.

---

## 11. Determinismo

Toda a estocasticidade passa por `engine.rng` (uma única `random.Random(seed)`):

- incidentes, ultrapassagens, clima dinâmico e ruído de deslocamento;
- duração de cada parada (`PIT_STOP_NOISE_S`).

Os perfis por piloto usam `CRC32(seed, driver_id)` e não consomem o RNG. Com a
mesma seed, o mesmo grid e a mesma configuração, a corrida é reproduzível.

---

## 12. Constantes principais

| Constante | Valor | Onde |
|---|---|---|
| `MIN_CAR_GAP_M` | `8.0` m | `state.py` |
| `GRID_SPACING_M` | `8.0` m | `run.py` |
| `GRID_REFERENCE_VELOCITY_MS` | `60.0` m/s | `run.py` |
| `DEFAULT_HORIZON` | `15` voltas | `strategy/config.py` |
| `STINT` | `15` voltas | `strategy/config.py` |
| `PACE_SPREAD_MS` | `0.5` m/s | `strategy/config.py` |
| `TYRE_MANAGEMENT_SPREAD` | `0.10` | `strategy/config.py` |
| `PIT_CREW_SPREAD_S` | `0.8` s | `strategy/config.py` |
| `PIT_STOP_NOISE_S` | `0.3` s | `strategy/config.py` |
| `AGGRESSION_JITTER` | `0.10` | `strategy/config.py` |
| `UNDERCUT_MIN_GAP_S` | `0.5` s | `strategy/config.py` |
| `UNDERCUT_GAP_THRESHOLD_S` | `1.8` s | `strategy/config.py` |
| `UNDERCUT_REACTION_WINDOW_LAPS` | `1` volta | `strategy/config.py` |
| `OVERTAKE_MAX_GAP_S` | `0.8` s | `overtaking.py` |
| `DRS_GAP_THRESHOLD_S` | `1.0` s | `physics.py` |

---

## 13. Como rodar e testar

A partir de `backend/`:

```bash
# Testes do motor e da estratégia
python -m pytest sim tests/test_strategy.py -q

# Lint
python -m ruff check .

# Smoke síncrono de física (não usa RaceEngine; avança tick() direto)
python -m sim.run --laps 3 --seed 42
```

Exemplo mínimo com o motor completo:

```python
from sim.engine import RaceEngine
from sim.run import montar_grid_inicial
from sim.track import TrackMap

estado = montar_grid_inicial(track_length=4309.0)
estado.total_laps = 58

motor = RaceEngine(
    race_state=estado,
    track_map=TrackMap.load("interlagos"),
    seed=42,
    weather="DRY",
    base_tick_delay=0.0,
)

for _ in range(estado.total_laps):
    motor.step_lap()
```

Para acompanhar as decisões de um piloto, `motor.get_lap_update_envelope()`
devolve o snapshot pronto para o Contrato D2.

---

## 14. Limitações e pontos de extensão

- O pelotão ainda larga fisicamente colado (8 m). Os perfis de ritmo abrem gaps
  ao longo da corrida, mas a ordem é moldada pelo bloqueio físico e pelas
  ultrapassagens.
- O undercut é intencionalmente conservador em bandeira verde; sob SC/VSC o
  pelotão pode parar junto (comportamento realista).
- A estratégia disponível na árvore atual é a heurística (`strategy/heuristic.py`).
  Não há otimizador de Monte Carlo no pacote.
- `pit_time_loss_s` e `pit_speed_limit_ms` vêm do `TrackMap`; circuitos sem a zona
  `pit_lane` usam os fallbacks.
- Novos comportamentos de estratégia devem entrar em `strategy/` ou como
  parâmetros passados pelo motor (como `pit_lane_loss_s` e `degradation_curve`),
  preservando a pureza de `sim/`.
