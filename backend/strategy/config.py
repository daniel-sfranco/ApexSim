"""Constantes e hiperparâmetros da heurística de estratégia de pit stop."""

STINT: int = 15
DEFAULT_HORIZON: int = 15
DEFAULT_PIT_STOP_DURATION: float = 2.5  # Tempo médio estático de troca de pneus (segundos)
DEFAULT_WARMUP_PENALTY: float = 1.0  # Penalidade térmica na out-lap (segundos)
DEFAULT_AGGRESSION: float = 0.5  # Agressividade neutra padrão

# Fatores das camadas reativas (Passo 3)
SAFETY_CAR_COST_FACTOR: float = 0.55  # Perda relativa de tempo cai para ~55% sob SC/VSC
UNDERCUT_GAP_THRESHOLD: float = 2.5  # Gap máximo (s) para considerar o carro atrás um rival direto
UNDERCUT_MIN_AGE: int = 10  # Idade mínima de pneu (voltas) para justificar resposta ao undercut

# Fatores das camadas reativas (Passo 3)
SAFETY_CAR_COST_FACTOR: float = 0.55  # Perda relativa de tempo cai para ~55% sob SC/VSC
UNDERCUT_GAP_THRESHOLD: float = 2.5  # Gap máximo (s) para considerar o carro atrás um rival direto
UNDERCUT_MIN_AGE: int = 10  # Idade mínima de pneu (voltas) para justificar resposta ao undercut
