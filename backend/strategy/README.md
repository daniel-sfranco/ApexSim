# Módulo de Estratégia de Pit Stop (Marcos M3 e M4)

Este módulo implementa a arquitetura de estratégia de pit stop do **ApexSim** em dois degraus:
- **Degrau 1 (`heuristic.py`, M3):** Avaliador heurístico de custo-benefício com regras reativas.
- **Degrau 2 (`monte_carlo.py`, M4):** Otimizador estocástico por Monte Carlo que simula $K$ cenários futuros sob incerteza usando *Common Random Numbers (CRN)*.

Documentação matemática completa em [`docs/estrategia.md`](../../docs/estrategia.md).

---

## 1. Contratos de Dados

### `PitDecision`
Objeto de retorno emitido para cada piloto (Degraus 1 e 2):
* `should_pit (bool)`: `True` se o piloto deve realizar o pit stop na próxima volta.
* `target_compound (str | None)`: Composto sugerido para o próximo stint (`"soft"`, `"medium"`, `"hard"`, `"wet"`).
* `reason (str)`: Motivo da decisão:
  * `"DEGRADATION"`: Prejuízo acumulado de desgaste superou o custo da parada.
  * `"SAFETY_CAR"`: Parada barata antecipada sob Safety Car / VSC.
  * `"RED_FLAG"`: Troca gratuita de pneus sob bandeira vermelha.
  * `"WEATHER"`: Incompatibilidade entre pneus e clima (ex: slick na chuva).
  * `"UNDERCUT"`: Resposta defensiva a parada de rival direto logo atrás.
  * `"STAY_OUT"`: Continuar na pista.

### `StrategyCandidate` e `MonteCarloPlan` (M4)
Retornados por `MonteCarloStrategyOptimizer.optimize_driver(...)`:
* `StrategyCandidate`: `(pit_offset, target_compound, expected_cost_s, std_cost_s, score_s)`.
* `MonteCarloPlan`: encapsula `decision` (`PitDecision`), `optimal_pit_lap`, `best_compound`, `candidates` (ordenados por `score_s`) e `num_scenarios`.

---

## 2. Lógica de Decisão e Regras de Negócio

A avaliação segue uma cascata de prioridades:

1. **Bandeira Vermelha (`RED_FLAG`):** Corrida paralisada nos boxes. O custo da parada é zero segundos, portanto a troca para o composto ideal é sempre agendada.
2. **Crossover Climático (`WEATHER`):** Troca imediata nos 3 estados climáticos (`dry`/`damp`/`wet`, aceitando também `seco`/`umido`/`molhado`): slick no úmido $\to$ `"intermediate"`, slick/intermediário no molhado $\to$ `"wet"`, pneu de chuva no seco $\to$ slick.
3. **Safety Car / VSC (`SAFETY_CAR`):** Como os carros em pista andam devagar, a perda relativa de tempo no pit cai em $\approx 45\%$ (`factor = 0.55`). Pilotos na janela aproveitam para antecipar a parada.
4. **Undercut Defensivo (`UNDERCUT`):** Se o rival imediatamente atrás ($\le 2.5\text{s}$) parou na volta anterior com pneu novo e o pneu do piloto atual já possui desgaste moderado ($\ge 10$ voltas), para na volta seguinte para proteger a posição.
5. **Degradação / Monte Carlo (`DEGRADATION`):**
   - No **Degrau 1**, compara o ganho de ritmo nas próximas $H$ voltas com pneu novo contra o custo ajustado da parada.
   - No **Degrau 2**, simula $K$ cenários futuros (ruído de degradação, ruído no tempo de box, probabilidade de Safety Car futuro e, opcionalmente, transições climáticas pela Cadeia de Markov de `sim/weather.py` com `dynamic_weather=True`) para avaliar múltiplos compostos e janelas de parada, ponderando custo médio e risco ($\mu + \lambda \sigma$).
6. **Seleção de Composto Alvo:** No seco, seleciona o pneu ideal para as voltas restantes ($\le 15$ macio, $\le 30$ médio, $> 30$ duro) e aplica a regra FIA de **não trocar para o mesmo composto** de forma consecutiva (ex.: Médio $\to$ Duro/Macio).

---

## 3. Como Integrar no Motor de Simulação (`RaceEngine`)

O contrato `evaluate_driver(...) -> PitDecision` é idêntico para ambos os degraus. Para usar o otimizador de Monte Carlo (M4):

```python
from sim.physics import tyre_time_loss
from sim.state import PitStatus, TyreCompound
from strategy import MonteCarloStrategyOptimizer

# 1. Instanciação única na inicialização da corrida
team_aggression = {
    "Red Bull": 0.9,
    "Ferrari": 0.8,
    "Mercedes": 0.7,
    "McLaren": 0.7,
    "Aston Martin": 0.5,
    "Alpine": 0.4,
    "Williams": 0.3,
    "Haas": 0.2,
    "Kick Sauber": 0.1,
    "RB": 0.5,
}
strategy = MonteCarloStrategyOptimizer(
    team_aggression=team_aggression,
    num_scenarios=64,
    seed=42,
)

# 2. A cada volta concluída no tick():
for driver in race_state.drivers.values():
    decision = strategy.evaluate_driver(
        driver_state=driver,
        race_state=race_state,
        pit_lane_loss_s=pit_lane_loss_s,  # ex: 21.0s vindo do TrackMap
        degradation_curve=lambda comp, age: tyre_time_loss(comp, age, track_temp=35.0),
    )

    if decision.should_pit:
        driver.pit_status = PitStatus.ENTERING
        # Na volta seguinte, o motor aplica a troca:
        # driver.tyre_compound = TyreCompound[decision.target_compound.upper()]
        # driver.tyre_age = 0
```

---

## 4. Como Executar os Testes Unitários

```bash
# Executar as suítes de testes da estratégia (M3 + M4)
backend/.venv/bin/pytest -o cache_dir=/tmp/pytest_cache backend/tests/test_strategy.py backend/tests/test_monte_carlo.py -v

# Validação de código e linter
backend/.venv/bin/ruff check --no-cache backend/strategy backend/tests/test_strategy.py backend/tests/test_monte_carlo.py
backend/.venv/bin/ruff format --check --no-cache backend/strategy backend/tests/test_strategy.py backend/tests/test_monte_carlo.py
```

