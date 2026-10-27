# Módulo de Estratégia de Pit Stop (Marco M3)

Este módulo implementa o avaliador heurístico de estratégias de pit stop do **ApexSim**. Ele é consultado a cada volta concluída pelo loop do motor de simulação (`RaceEngine.tick()`) para decidir se cada um dos 20 pilotos deve ir para o pit lane na volta seguinte.

---

## 1. Contrato de Dados

### `PitDecision`
Objeto de retorno emitido para cada piloto:
* `should_pit (bool)`: `True` se o piloto deve realizar o pit stop na próxima volta.
* `target_compound (str | None)`: Composto sugerido para o próximo stint (`"soft"`, `"medium"`, `"hard"`, `"wet"`).
* `reason (str)`: Motivo da decisão:
  * `"DEGRADATION"`: Prejuízo acumulado de desgaste superou o custo da parada.
  * `"SAFETY_CAR"`: Parada barata antecipada sob Safety Car / VSC.
  * `"RED_FLAG"`: Troca gratuita de pneus sob bandeira vermelha.
  * `"WEATHER"`: Incompatibilidade entre pneus e clima (ex: slick na chuva).
  * `"UNDERCUT"`: Resposta defensiva a parada de rival direto logo atrás.
  * `"STAY_OUT"`: Continuar na pista.

---

## 2. Lógica de Decisão e Regras de Negócio

A avaliação segue uma cascata de prioridades:

1. **Bandeira Vermelha (`RED_FLAG`):** Corrida paralisada nos boxes. O custo da parada é zero segundos, portanto a troca para o composto ideal é sempre agendada.
2. **Crossover Climático (`WEATHER`):** Troca imediata se o pneu for inadequado para a pista (slick na chuva $\to$ `"wet"`; pneu de chuva no seco $\to$ slick).
3. **Safety Car / VSC (`SAFETY_CAR`):** Como os carros em pista andam devagar, a perda relativa de tempo no pit cai em $\approx 45\%$ (`factor = 0.55`). Pilotos que já rodaram mais de 8 a 13 voltas aproveitam para antecipar a parada.
4. **Undercut Defensivo (`UNDERCUT`):** Se o rival imediatamente atrás ($\le 2.5\text{s}$) parou na volta anterior com pneu novo e o pneu do piloto atual já possui desgaste moderado ($\ge 10$ voltas), para na volta seguinte para proteger a posição.
5. **Algoritmo Base de Degradação (`DEGRADATION`):** Compara o ganho de ritmo nas próximas $H$ voltas com um pneu novo contra o custo total da parada (pit lane + 2.5s de troca + 1.0s de aquecimento), modulado pela agressividade da equipe ($0.0$ a $1.0$).
6. **Seleção de Composto Alvo:** No seco, seleciona o pneu ideal para as voltas restantes ($\le 15$ macio, $\le 30$ médio, $> 30$ duro) e aplica a regra FIA de **não trocar para o mesmo composto** de forma consecutiva (ex.: Médio $\to$ Duro/Macio).

---

## 3. Como Integrar no Motor de Simulação (`RaceEngine`)

O Gabriel ou quem estiver desenvolvendo o motor precisa apenas importar a classe e consultá-la dentro de cada volta:

```python
from sim.physics import tyre_time_loss
from sim.state import PitStatus, TyreCompound
from strategy.heuristic import PitStrategyHeuristic

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
heuristic = PitStrategyHeuristic(team_aggression=team_aggression)

# 2. A cada volta concluída no tick():
for driver in race_state.drivers.values():
    decision = heuristic.evaluate_driver(
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
# Executar a suíte de testes da estratégia
backend/.venv/bin/pytest backend/tests/test_strategy.py -v

# Validação de código e linter
backend/.venv/bin/ruff check --no-cache backend/strategy backend/tests/test_strategy.py
```

