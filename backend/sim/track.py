"""Modelo de dados semântico do mapa de pistas (Contrato D4) — Domínio Puro (sim).

Consumido pela Física & Eventos Estocásticos (Isaac) e pelo Motor de Simulação (Gabriel).
Permite consultas lineares em 1D sobre as zonas homologadas da pista.
Zero dependências externas: código puramente matemático em memória.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Localiza diretório de track_maps a partir da raiz do repositório
DEFAULT_TRACK_MAPS_DIR = Path(__file__).resolve().parent.parent.parent / "track_maps"

# Fallbacks usados quando o circuito não anota a zona `pit_lane` (Contrato D4).
# Valores equivalentes à média dos circuitos homologados do projeto.
PIT_LANE_FALLBACK_SPEED_LIMIT_KMH = 80.0
PIT_LANE_FALLBACK_TIME_LOSS_S = 22.0

# Cascata de fallback para zonas de ultrapassagem. Circuitos anotados antes do
# tipo `overtaking_spot` (ex.: Interlagos) usam as ativações de DRS como
# oportunidade. Zonas de frenagem ficam de fora: são áreas de risco para o
# gerador de incidentes, não pontos de ultrapassagem homologados.
OVERTAKING_ZONE_PREFERENCE: tuple[str, ...] = (
    "overtaking_spot",
    "drs_activation",
)


@dataclass(frozen=True)
class Zone:
    """Uma zona semântica anotada na pista."""

    type: str
    start_m: float
    end_m: float
    props: dict[str, Any] = field(default_factory=dict)

    @property
    def is_point(self) -> bool:
        """Indica se a zona é um evento pontual (largura zero)."""
        return self.start_m == self.end_m

    @property
    def length_m(self) -> float:
        """Extensão linear da zona em metros."""
        return self.end_m - self.start_m

    def contains(self, distance_m: float) -> bool:
        """Verifica se uma coordenada de distância linear está dentro desta zona."""
        if self.is_point:
            return abs(self.start_m - distance_m) < 1e-3
        return self.start_m <= distance_m <= self.end_m


@dataclass
class TrackMap:
    """Mapa semântico completo de um circuito (Contrato D4)."""

    circuit_id: str
    length_m: int
    points: list[dict[str, float]]
    zones: list[Zone]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackMap:
        """Constrói uma instância de TrackMap a partir de um dicionário serializado."""
        zones = [
            Zone(
                type=z["type"],
                start_m=float(z["start_m"]),
                end_m=float(z["end_m"]),
                props=z.get("props", {}),
            )
            for z in data.get("zones", [])
        ]
        return cls(
            circuit_id=data["circuit_id"],
            length_m=int(data["length_m"]),
            points=data.get("points", []),
            zones=zones,
        )

    @classmethod
    def load(cls, circuit_id_or_path: str | Path, base_dir: Path | None = None) -> TrackMap:
        """Carrega um circuito pelo ID (ex: 'interlagos') ou pelo caminho completo do JSON."""
        caminho = Path(circuit_id_or_path)
        if not caminho.exists() and not caminho.is_absolute():
            dir_busca = base_dir or DEFAULT_TRACK_MAPS_DIR
            caminho = dir_busca / f"{circuit_id_or_path}.json"
            if not caminho.exists():
                # Tenta fallback para pasta local track_maps/
                caminho = Path("track_maps") / f"{circuit_id_or_path}.json"

        if not caminho.exists():
            raise FileNotFoundError(f"Mapa de pista não encontrado: {caminho}")

        data = json.loads(caminho.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def get_zones_at(self, distance_m: float) -> list[Zone]:
        """Devolve todas as zonas ativas que englobam a distância informada."""
        d = distance_m % self.length_m if self.length_m > 0 else distance_m
        return [z for z in self.zones if z.contains(d)]

    def get_active_sector(self, distance_m: float) -> int:
        """Devolve o número do setor atual (1, 2 ou 3) para a posição do carro."""
        d = distance_m % self.length_m if self.length_m > 0 else distance_m
        for z in self.zones:
            if z.type == "sector" and z.contains(d):
                return int(z.props.get("number", 1))
        return 1

    def get_braking_zone_at(self, distance_m: float) -> Zone | None:
        """Retorna a zona de frenagem na coordenada, se o carro estiver em uma.

        Utilizado pelo gerador de acidentes do Isaac para modular probabilidade e Safety Car.
        """
        d = distance_m % self.length_m if self.length_m > 0 else distance_m
        for z in self.zones:
            if z.type == "braking_zone" and z.contains(d):
                return z
        return None

    def is_drs_active(self, distance_m: float) -> bool:
        """Retorna True se o ponto atual faz parte de uma zona de ativação de DRS."""
        d = distance_m % self.length_m if self.length_m > 0 else distance_m
        return any(z.type == "drs_activation" and z.contains(d) for z in self.zones)

    def is_in_pit_lane(self, distance_m: float) -> bool:
        """Retorna True se a coordenada linear está dentro do pit lane."""
        d = distance_m % self.length_m if self.length_m > 0 else distance_m
        return any(z.type == "pit_lane" and z.contains(d) for z in self.zones)

    # ------------------------------------------------------------------
    # Pit lane (Contrato D4)
    # ------------------------------------------------------------------

    def get_pit_lane_zone(self) -> Zone | None:
        """Zona `pit_lane` do circuito (None quando não anotada)."""
        for z in self.zones:
            if z.type == "pit_lane":
                return z
        return None

    def pit_speed_limit_kmh(self) -> float:
        """Limite de velocidade do pit lane em km/h, com fallback seguro."""
        zone = self.get_pit_lane_zone()
        if zone is not None:
            try:
                limit = float(zone.props.get("speed_limit_kmh"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                limit = 0.0
            if limit > 0.0:
                return limit
        return PIT_LANE_FALLBACK_SPEED_LIMIT_KMH

    def pit_speed_limit_ms(self) -> float:
        """Limite de velocidade do pit lane convertido para m/s."""
        return self.pit_speed_limit_kmh() / 3.6

    def pit_time_loss_s(self) -> float:
        """Perda total de tempo (s) ao atravessar o pit lane, com fallback seguro."""
        zone = self.get_pit_lane_zone()
        if zone is not None:
            try:
                loss = float(zone.props.get("time_loss_s"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                loss = 0.0
            if loss > 0.0:
                return loss
        return PIT_LANE_FALLBACK_TIME_LOSS_S

    # ------------------------------------------------------------------
    # Zonas de ultrapassagem / DRS
    # ------------------------------------------------------------------

    def get_drs_activation_zone_at(self, distance_m: float) -> Zone | None:
        """Zona de ativação de DRS que contém a coordenada, se houver."""
        d = distance_m % self.length_m if self.length_m > 0 else distance_m
        for z in self.zones:
            if z.type == "drs_activation" and z.contains(d):
                return z
        return None

    def get_overtaking_zone_at(self, distance_m: float, *, fallback: bool = True) -> Zone | None:
        """Zona onde uma ultrapassagem é plausível na coordenada informada.

        Com ``fallback=True``, circuitos sem `overtaking_spot` anotada (ex.:
        Interlagos) usam as zonas `drs_activation` como oportunidade de
        ultrapassagem, respeitando :data:`OVERTAKING_ZONE_PREFERENCE`.
        """
        d = distance_m % self.length_m if self.length_m > 0 else distance_m
        tipos = OVERTAKING_ZONE_PREFERENCE if fallback else OVERTAKING_ZONE_PREFERENCE[:1]
        for zone_type in tipos:
            for z in self.zones:
                if z.type == zone_type and z.contains(d):
                    return z
        return None
