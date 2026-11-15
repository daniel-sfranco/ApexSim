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
from dataclasses import dataclass
from typing import Literal

WeatherState = Literal["seco", "umido", "molhado"]

# HIPÓTESE DE MODELAGEM (docs/fisica.md Seção 6.4 — ausência de matriz FIA publicada):
# Matriz de transição por volta para cenário de clima instável.
# Linhas: estado atual (seco, umido, molhado) -> Colunas: próximo estado.
DEFAULT_TRANSITION_PROBABILITIES: dict[WeatherState, dict[WeatherState, float]] = {
    "seco": {"seco": 0.95, "umido": 0.04, "molhado": 0.01},
    "umido": {"seco": 0.20, "umido": 0.65, "molhado": 0.15},
    "molhado": {"seco": 0.02, "umido": 0.23, "molhado": 0.75},
}

# HIPÓTESE DE MODELAGEM: proxy discreto de severidade de água theta in [0.0, 1.0] por estado
NOMINAL_TRACK_WETNESS: dict[WeatherState, float] = {
    "seco": 0.0,
    "umido": 0.40,
    "molhado": 0.85,
}

# Penalidade de ritmo (s/volta adicionais em relação ao slick em pista seca).
# - O valor de +3.0 s para 'wet' em pista 'molhado' vem de [29] (docs/fisica.md Seção 6.4).
# - Todos os demais valores fora da diagonal são HIPÓTESES DE MODELAGEM escolhidas para
#   garantir o crossover físico entre Slick, Intermediate e Full Wet (Seção 6.2).
WEATHER_COMPOUND_TIME_PENALTIES: dict[WeatherState, dict[str, float]] = {
    "seco": {
        "soft": 0.0,
        "medium": 0.0,
        "hard": 0.0,
        "intermediate": 3.6,  # hipótese: superaquecimento e menor área de contato no seco
        "wet": 7.8,  # hipótese: blocos altos e rápida degradação térmica no seco
    },
    "umido": {
        "soft": 5.5,  # hipótese: perda de aderência em lâmina d'água fina
        "medium": 6.0,  # hipótese
        "hard": 7.0,  # hipótese: composto duro esfria e perde janela térmica
        "intermediate": 1.2,  # hipótese: composto ótimo na janela úmida (crossover)
        "wet": 4.5,  # hipótese: excesso de drenagem / menor grip mecânico que Inter
    },
    "molhado": {
        "soft": 18.0,  # hipótese: aquaplanagem severa com pneu liso
        "medium": 19.5,  # hipótese
        "hard": 22.0,  # hipótese
        "intermediate": 6.8,  # hipótese: saturação da capacidade de drenagem do Inter
        "wet": 3.0,  # literatura [29]: +3,0 s/volta ref. base em chuva forte
    },
}

# HIPÓTESE DE MODELAGEM: multiplicador de aderência mecânica [0.1, 1.0] derivado de
# forma monotônica às penalidades acima (usado para modular risco de incidente em events.py).
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


def normalize_compound_name(compound: str) -> str:
    """Normaliza o nome do composto para minúsculas e remove prefixos de Enum."""
    c = compound.lower().strip()
    if "." in c:
        c = c.split(".")[-1]
    if c in ("soft", "medium", "hard", "intermediate", "wet"):
        return c
    if c == "inter":
        return "intermediate"
    return c


def weather_time_delta(compound: str, weather_state: WeatherState | str) -> float:
    """Retorna segundos adicionais de tempo de volta pela interação composto x clima."""
    state_key = weather_state.lower().strip()
    if state_key not in WEATHER_COMPOUND_TIME_PENALTIES:
        raise ValueError(
            f"Estado climático desconhecido: '{weather_state}'. "
            "Esperado: 'seco', 'umido' ou 'molhado'."
        )

    c_norm = normalize_compound_name(compound)
    penalties = WEATHER_COMPOUND_TIME_PENALTIES[state_key]  # type: ignore[index]
    if c_norm not in penalties:
        raise ValueError(
            f"Composto desconhecido: '{compound}'. Esperado: soft, medium, hard, intermediate, wet."
        )

    return penalties[c_norm]


def weather_grip_factor(compound: str, weather_state: WeatherState | str) -> float:
    """Retorna o multiplicador de aderência [0.1, 1.0] pela interação composto x clima."""
    state_key = weather_state.lower().strip()
    if state_key not in WEATHER_COMPOUND_GRIP:
        raise ValueError(
            f"Estado climático desconhecido: '{weather_state}'. "
            "Esperado: 'seco', 'umido' ou 'molhado'."
        )

    c_norm = normalize_compound_name(compound)
    grips = WEATHER_COMPOUND_GRIP[state_key]  # type: ignore[index]
    if c_norm not in grips:
        raise ValueError(
            f"Composto desconhecido: '{compound}'. Esperado: soft, medium, hard, intermediate, wet."
        )

    return grips[c_norm]


@dataclass
class WeatherSimulator:
    """Simulador climático dinâmico por Cadeia de Markov (docs/fisica.md Seção 6.1)."""

    current_state: WeatherState = "seco"
    transition_probs: dict[WeatherState, dict[WeatherState, float]] | None = None

    def __post_init__(self) -> None:
        if self.transition_probs is None:
            self.transition_probs = DEFAULT_TRANSITION_PROBABILITIES

    @property
    def wetness(self) -> float:
        """Proxy discreto de severidade de água na pista theta in [0.0, 1.0]."""
        return NOMINAL_TRACK_WETNESS[self.current_state]

    def advance_lap(self, rng: random.Random | None = None) -> WeatherState:
        """Avança uma volta na cadeia de Markov usando o gerador `rng`."""
        r = rng if rng is not None else random.Random()
        assert self.transition_probs is not None
        row = self.transition_probs[self.current_state]

        states = list(row.keys())
        probs = list(row.values())

        next_state = r.choices(states, weights=probs, k=1)[0]
        self.current_state = next_state
        return self.current_state

    def time_delta(self, compound: str) -> float:
        """Penalidade de tempo na volta para o composto no estado climático atual."""
        return weather_time_delta(compound, self.current_state)

    def grip_factor(self, compound: str) -> float:
        """Fator de aderência para o composto no estado climático atual."""
        return weather_grip_factor(compound, self.current_state)
