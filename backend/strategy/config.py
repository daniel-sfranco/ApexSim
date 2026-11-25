"""Constantes e hiperparâmetros da heurística de estratégia de pit stop."""

STINT: int = 15
DEFAULT_HORIZON: int = 15
DEFAULT_PIT_STOP_DURATION: float = 2.5  # Tempo médio estático de troca de pneus (segundos)
DEFAULT_WARMUP_PENALTY: float = 1.0  # Penalidade térmica na out-lap (segundos)
DEFAULT_AGGRESSION: float = 0.5  # Agressividade neutra padrão

# Agressividade base por equipe para diferenciar estratégias
DEFAULT_TEAM_AGGRESSION: dict[str, float] = {
    "Red Bull": 0.8,
    "Ferrari": 0.7,
    "McLaren": 0.75,
    "Mercedes": 0.65,
    "Aston Martin": 0.55,
    "Alpine": 0.5,
    "Williams": 0.45,
    "RB": 0.4,
    "Kick Sauber": 0.35,
    "Haas": 0.3,
}

# Fatores das camadas reativas (Passo 3)
SAFETY_CAR_COST_FACTOR: float = 0.55  # Perda relativa de tempo cai para ~55% sob SC/VSC
UNDERCUT_GAP_THRESHOLD: float = 2.5  # Gap máximo (s) para considerar o carro atrás um rival direto
UNDERCUT_MIN_AGE: int = 10  # Idade mínima de pneu (voltas) para justificar resposta ao undercut
