"""
sim/weather.py

Modelo Climático Dinâmico (Cadeia de Markov e Crossover de Compostos) para o ApexSim (Marco M4).
Fundamentação matemática em docs/fisica.md (Seção 6).

Distinção explícita entre Literatura/Regulamento e Hipóteses de Modelagem:
1. Estrutura de Markov (Seção 6.1, SFU STAT 380 [31]) e regra operacional de pneus de
   chuva (Seção 6.4, FIA Art. B6.1.1 / B6.3.7 [30]): base teórica e regulatória.
2. Referência quantitativa de literatura (Seção 6.4, Mintlify F1 ML [29]): penalidade base
   de ritmo do Full Wet em chuva forte de ~+3,0 s/volta (com degradação ~0,035 s/volta) e
   degradação do Intermediário em chuva leve de ~0,060 s/volta.
3. HIPÓTESES DE MODELAGEM (parâmetros heurísticos de engenharia sem tabela oficial FIA):
   - probabilidades da matriz de transição `DEFAULT_TRANSITION_PROBABILITIES` (dentro das
     faixas sugeridas na Seção 6.4 para corridas de tempo instável);
   - níveis nominais de água na pista `NOMINAL_TRACK_WETNESS` (theta in [0, 1]);
   - matriz de penalidades cruzadas `WEATHER_COMPOUND_TIME_PENALTIES` e fatores de grip
     `WEATHER_COMPOUND_GRIP` fora do ponto de referência de +3,0 s do Wet, construídos
     para reproduzir o ordenamento qualitativo de crossover:
       * Seco:    Slick < Intermediate < Wet
       * Úmido:   Intermediate < Wet < Slick
       * Molhado: Wet < Intermediate < Slick
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from sim.physics import normalize_compound_name

WeatherState = Literal["seco", "umido", "molhado"]

# Matriz de transição por volta para corrida com clima dinâmico (docs/fisica.md Seção 6.4).
# Persistência elevada em todos os estados para evitar oscilações artificiais a cada 2-3 voltas
# (ping-pong de pit stops): ~63% das corridas de 58 voltas iniciadas no seco permanecem secas,
# e janelas de pista úmida/molhada duram em média ~7-10 voltas.
DEFAULT_TRANSITION_PROBABILITIES: dict[WeatherState, dict[WeatherState, float]] = {
    "seco": {"seco": 0.992, "umido": 0.007, "molhado": 0.001},
    "umido": {"seco": 0.08, "umido": 0.85, "molhado": 0.07},
    "molhado": {"seco": 0.01, "umido": 0.09, "molhado": 0.90},
}

# Severidade nominal de água na pista theta in [0.0, 1.0].
NOMINAL_TRACK_WETNESS: dict[WeatherState, float] = {
    "seco": 0.0,
    "umido": 0.40,
    "molhado": 0.85,
}

# Penalidade de ritmo (s/volta adicionais vs. slick no seco).
# O valor de +3.0 s para 'wet' em 'molhado' vem de [29]; os demais garantem o crossover.
WEATHER_COMPOUND_TIME_PENALTIES: dict[WeatherState, dict[str, float]] = {
    "seco": {
        "soft": 0.0,
        "medium": 0.0,
        "hard": 0.0,
        "intermediate": 3.6,
        "wet": 7.8,
    },
    "umido": {
        "soft": 5.5,
        "medium": 6.0,
        "hard": 7.0,
        "intermediate": 1.2,
        "wet": 4.5,
    },
    "molhado": {
        "soft": 18.0,
        "medium": 19.5,
        "hard": 22.0,
        "intermediate": 6.8,
        "wet": 3.0,
    },
}

# Multiplicador de aderência mecânica [0.1, 1.0] usado na taxa de incidentes em events.py.
WEATHER_COMPOUND_GRIP: dict[WeatherState, dict[str, float]] = {
    "seco": {
        "soft": 1.0,
        "medium": 1.0,
        "hard": 1.0,
        "intermediate": 0.82,
        "wet": 0.68,
    },
    "umido": {
        "soft": 0.62,
        "medium": 0.58,
        "hard": 0.52,
        "intermediate": 0.90,
        "wet": 0.78,
    },
    "molhado": {
        "soft": 0.25,
        "medium": 0.22,
        "hard": 0.18,
        "intermediate": 0.65,
        "wet": 0.88,
    },
}


WEATHER_ALIAS_TO_STATE: dict[str, WeatherState] = {
    "seco": "seco",
    "dry": "seco",
    "umido": "umido",
    "úmido": "umido",
    "damp": "umido",
    "molhado": "molhado",
    "wet": "molhado",
}

WEATHER_STATE_TO_CONTRACT: dict[WeatherState, str] = {
    "seco": "DRY",
    "umido": "DAMP",
    "molhado": "WET",
}


def normalize_weather_state(
    weather: WeatherState | str,
    *,
    default: WeatherState | None = None,
) -> WeatherState:
    """Normaliza estados climáticos PT/D2 (`DRY`/`DAMP`/`WET` ou `seco`/`umido`/`molhado`)."""
    key = str(weather).lower().strip()
    resolved = WEATHER_ALIAS_TO_STATE.get(key)
    if resolved is not None:
        return resolved
    if default is not None:
        return default
    raise ValueError(
        f"Estado climático desconhecido: '{weather}'. "
        "Esperado: 'seco'/'DRY', 'umido'/'DAMP' ou 'molhado'/'WET'."
    )


def weather_state_to_contract(weather_state: WeatherState | str) -> str:
    """Converte o estado climático interno para o enum do Contrato D2 (`DRY`/`DAMP`/`WET`)."""
    return WEATHER_STATE_TO_CONTRACT[normalize_weather_state(weather_state)]


def weather_time_delta(compound: str, weather_state: WeatherState | str) -> float:
    """Retorna segundos adicionais de tempo de volta pela interação composto x clima."""
    state_key = normalize_weather_state(weather_state)

    c_norm = normalize_compound_name(compound)
    penalties = WEATHER_COMPOUND_TIME_PENALTIES[state_key]
    if c_norm not in penalties:
        raise ValueError(
            f"Composto desconhecido: '{compound}'. Esperado: soft, medium, hard, intermediate, wet."
        )

    return penalties[c_norm]


def weather_grip_factor(compound: str, weather_state: WeatherState | str) -> float:
    """Retorna o multiplicador de aderência [0.1, 1.0] pela interação composto x clima."""
    state_key = normalize_weather_state(weather_state)

    c_norm = normalize_compound_name(compound)
    grips = WEATHER_COMPOUND_GRIP[state_key]
    if c_norm not in grips:
        raise ValueError(
            f"Composto desconhecido: '{compound}'. Esperado: soft, medium, hard, intermediate, wet."
        )

    return grips[c_norm]


@dataclass
class WeatherSimulator:
    """Simulador climático dinâmico por Cadeia de Markov (docs/fisica.md Seção 6.1)."""

    current_state: WeatherState = "seco"
    transition_probs: dict[WeatherState, dict[WeatherState, float]] = field(
        default_factory=lambda: DEFAULT_TRANSITION_PROBABILITIES
    )

    @property
    def wetness(self) -> float:
        """Proxy discreto de severidade de água na pista theta in [0.0, 1.0]."""
        return NOMINAL_TRACK_WETNESS[self.current_state]

    def advance_lap(self, rng: random.Random | None = None) -> WeatherState:
        """Avança uma volta na cadeia de Markov usando o gerador `rng`."""
        r = rng if rng is not None else random.Random()
        row = self.transition_probs[self.current_state]
        next_state = r.choices(list(row.keys()), weights=list(row.values()), k=1)[0]
        self.current_state = next_state
        return self.current_state

    def time_delta(self, compound: str) -> float:
        """Penalidade de tempo na volta para o composto no estado climático atual."""
        return weather_time_delta(compound, self.current_state)

    def grip_factor(self, compound: str) -> float:
        """Fator de aderência para o composto no estado climático atual."""
        return weather_grip_factor(compound, self.current_state)
