"""Modelo de dados semântico do mapa de pistas (Contrato D4).

Consumido pela Física & Eventos Estocásticos (Isaac) e pelo Motor de Simulação (Gabriel).
Permite consultas lineares em 1D sobre as zonas homologadas da pista.
Reexporta a implementação de domínio puro de sim.track.
"""

from __future__ import annotations

from pathlib import Path

from app.config import TRACK_MAPS_DIR
from sim.track import TrackMap as CoreTrackMap
from sim.track import Zone as CoreZone

Zone = CoreZone


class TrackMap(CoreTrackMap):
    """Especialização de TrackMap com resolução de caminho via app.config.TRACK_MAPS_DIR."""

    @classmethod
    def load(cls, circuit_id_or_path: str | Path) -> TrackMap:
        core_instance = CoreTrackMap.load(circuit_id_or_path, base_dir=TRACK_MAPS_DIR)
        return cls(
            circuit_id=core_instance.circuit_id,
            length_m=core_instance.length_m,
            points=core_instance.points,
            zones=core_instance.zones,
        )


__all__ = ["Zone", "TrackMap"]
