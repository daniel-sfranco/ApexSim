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

# ---------------------------------------------------------------------------
# Dessincronização das estratégias (perfis por piloto)
# ---------------------------------------------------------------------------
# Desvio máximo de ritmo em m/s. Com ~60 m/s, +-0.5 m/s equivale a ~0.8% de
# tempo de volta: suficiente para o pelotão abrir gaps reais sem transformar a
# corrida em procissão.
PACE_SPREAD_MS: float = 0.5

# Desvio relativo máximo na curva de degradação (gestão de pneu do piloto).
TYRE_MANAGEMENT_SPREAD: float = 0.10

# Desvio máximo do tempo de pit crew por piloto, em segundos.
PIT_CREW_SPREAD_S: float = 0.8

# Ruído aplicado a cada parada individual, além do desvio do pit crew.
PIT_STOP_NOISE_S: float = 0.3

# Desvio máximo de agressividade somado à base da equipe.
AGGRESSION_JITTER: float = 0.10

# Gate do motor para a reação de undercut: só reage a um rival de fato próximo
# (mais restrito que o limiar da heurística), que já concluiu a parada na volta
# anterior e numa faixa de gap em que o undercut é uma ameaça real. Uma reação
# por stint evita a cascata no pelotão.
UNDERCUT_MIN_GAP_S: float = 0.5
UNDERCUT_GAP_THRESHOLD_S: float = 1.8
UNDERCUT_REACTION_WINDOW_LAPS: int = 1
