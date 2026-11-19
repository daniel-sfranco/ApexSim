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


def montar_grid_inicial(
    grid: list[str] | None = None,
    initial_tyres: dict[str, str] | None = None,
) -> RaceState:
    """Constrói um RaceState de largada com os pilotos no grid.

    Todos começam na volta 0, sem gap acumulado, tanque cheio e fora do pit.
    Serve como "estado zero" para os testes e como ponto de partida real da
    simulação.

    Args:
        grid: Códigos FIA na ordem de largada escolhida no setup. Quando
            omitido, usa o grid padrão de 20 pilotos.
        initial_tyres: Compostos iniciais por código (ex.: ``{"VER": "SOFT"}``).
            Compostos ausentes ou desconhecidos caem no MEDIUM.
    """
    if grid:
        pilotos = []
        for driver_id in grid:
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

        drivers[driver_id] = DriverState(
            driver_id=driver_id,
            name=name,
            team=team,
            position=grid_position,
            lap_distance_covered=0.0,
            total_distance_covered=0.0,
            current_lap=0,
            last_lap_time=None,
            gap_to_leader=0.0 if grid_position == 1 else float(grid_position - 1) * 0.3,
            gap_to_ahead=None if grid_position == 1 else 0.3,
            tyre_compound=composto,
            tyre_age=0,
            fuel_load=110.0,
            pit_status=PitStatus.NONE,
            pit_stops_made=0,
            is_retired=False,
            base_velocity=20.0,  # Velocidade base de volta em m/s
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
    race_state = montar_grid_inicial()
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
