import argparse
import random

from .state import (
    DriverState,
    PitStatus,
    RaceState,
    TrackStatus,
    TyreCompound,
    tick,
    todos_pilotos_finalizados,
)

GRID_20_PILOTOS = [
    ("VER", "Max Verstappen", "Red Bull"),
    ("PER", "Sergio Pérez", "Red Bull"),
    ("HAM", "Lewis Hamilton", "Mercedes"),
    ("RUS", "George Russell", "Mercedes"),
    ("ALB", "Alexander Albon", "Williams"),
    ("COL", "Franco Colapinto", "Williams"),
    ("NOR", "Lando Norris", "McLaren"),
    ("PIA", "Oscar Piastri", "McLaren"),
    ("ALO", "Fernando Alonso", "Aston Martin"),
    ("STR", "Lance Stroll", "Aston Martin"),
    ("GAS", "Pierre Gasly", "Alpine"),
    ("HUL", "Nico Hülkenberg", "Alpine"),
    ("LEC", "Charles Leclerc", "Ferrari"),
    ("SAI", "Carlos Sainz", "Ferrari"),
    ("TSU", "Yuki Tsunoda", "RB"),
    ("LAW", "Liam Lawson", "RB"),
    ("ZHO", "Zhou Guanyu", "Kick Sauber"),
    ("BOT", "Valtteri Bottas", "Kick Sauber"),
    ("OCO", "Esteban Ocon", "Haas"),
    ("MAG", "Kevin Magnussen", "Haas"),
]

# Catálogo usado quando o cliente envia o grid escolhido no setup. Inclui os
# pilotos da lista do frontend que não fazem parte do grid padrão acima.
PILOTOS_POR_CODIGO: dict[str, tuple[str, str]] = {
    driver_id: (name, team) for driver_id, name, team in GRID_20_PILOTOS
}

# Separação física entre dois slots consecutivos do grid (metros). Igual ao
# MIN_CAR_GAP_M (8.0 m) para não provocar bloqueio artificial na largada.
GRID_SPACING_M = 8.0
GRID_REFERENCE_VELOCITY_MS = 60.0
GRID_GAP_S = GRID_SPACING_M / GRID_REFERENCE_VELOCITY_MS


def montar_grid_inicial(
    grid: list[str] | None = None,
    initial_tyres: dict[str, str] | None = None,
    track_length: float = 4309.0,
) -> RaceState:
    """Constrói um RaceState de largada com os pilotos alinhados no grid.

    Os carros ficam atrás da linha de chegada, separados fisicamente por
    `GRID_SPACING_M`: P1 é o mais próximo da linha e cada posição seguinte fica
    8 m mais atrás. O `gap_to_ahead` correspondente é `GRID_GAP_S`.

    Serve como "estado zero" para os testes e como ponto de partida real da
    simulação. O primeiro cruzamento da linha é tratado pelo `tick()` como a
    largada (não conta volta).

    Args:
        grid: Códigos FIA na ordem de largada escolhida no setup. Quando
            omitido, usa o grid padrão de 20 pilotos.
        initial_tyres: Compostos iniciais por código (ex.: ``{"VER": "SOFT"}``).
            Compostos ausentes ou desconhecidos caem no MEDIUM.
        track_length: Extensão do circuito em metros, usada para posicionar o
            grid em relação à linha de chegada.
    """
    if grid:
        pilotos = []
        vistos: set[str] = set()
        for driver_id in grid:
            if driver_id in vistos:
                continue
            vistos.add(driver_id)
            name, team = PILOTOS_POR_CODIGO.get(driver_id, (driver_id, "Independent"))
            pilotos.append((driver_id, name, team))
    else:
        pilotos = GRID_20_PILOTOS

    drivers = {}
    for grid_position, (driver_id, name, team) in enumerate(pilotos, start=1):
        composto = TyreCompound.MEDIUM
        if initial_tyres and driver_id in initial_tyres:
            try:
                composto = TyreCompound[str(initial_tyres[driver_id]).strip().upper()]
            except KeyError:
                composto = TyreCompound.MEDIUM

        # Distância atrás da linha (P1 = 8 m, P2 = 16 m, ...). `lap_distance`
        # fica no intervalo válido [0, track_length) e `total_distance` negativo
        # preserva a ordem física antes da largada.
        offset_m = grid_position * GRID_SPACING_M
        if track_length > 0:
            lap_distance = (track_length - offset_m) % track_length
        else:
            lap_distance = 0.0

        drivers[driver_id] = DriverState(
            driver_id=driver_id,
            name=name,
            team=team,
            position=grid_position,
            lap_distance_covered=lap_distance,
            total_distance_covered=-offset_m,
            current_lap=0,
            last_lap_time=None,
            gap_to_leader=float(grid_position - 1) * GRID_GAP_S,
            gap_to_ahead=None if grid_position == 1 else GRID_GAP_S,
            tyre_compound=composto,
            tyre_age=0,
            fuel_load=110.0,
            pit_status=PitStatus.NONE,
            pit_stops_made=0,
            is_retired=False,
            base_velocity=GRID_REFERENCE_VELOCITY_MS,
            lap_time_sum=0.0,
            drs_active=False,
        )

    return RaceState(
        current_lap=0,
        total_laps=58,
        track_status=TrackStatus.GREEN,
        drivers=drivers,
        lap_history=[],
        elapsed_time=0.0,
        is_finished=False,
    )


def main():
    parser = argparse.ArgumentParser(description="Roda a simulação")

    # 2. Voltas
    parser.add_argument(
        "-l", "--laps", type=int, default=1, help="Quantidade de voltas a simular, default = 1"
    )

    # 3. Seed aleatória
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=1,
        help="Seed para a geração de números aleatórios (default: 1)",
    )
    args = parser.parse_args()
    random.seed(args.seed)
    race_state = montar_grid_inicial(track_length=3337.0)
    laps_alvo = min(args.laps, race_state.total_laps)
    while race_state.current_lap < laps_alvo:
        tick(race_state, delta_time=10.0, track_length=3337)
        print(f"{race_state.elapsed_time:.1f}s " + "#" * 50)
    # Na distância completa, segue até os pilotos da última volta cruzarem
    # a linha final (os da penúltima ou mais atrás já estão classificados).
    while race_state.current_lap >= race_state.total_laps and not todos_pilotos_finalizados(
        race_state
    ):
        tick(race_state, delta_time=10.0, track_length=3337)
        print(f"{race_state.elapsed_time:.1f}s " + "#" * 50)
    race_state.is_finished = todos_pilotos_finalizados(race_state)


if __name__ == "__main__":
    main()
