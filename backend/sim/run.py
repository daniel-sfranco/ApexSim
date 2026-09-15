import argparse
import random

from .state import (
    DriverState,
    PitStatus,
    RaceState,
    TrackStatus,
    TyreCompound,
    tick,
)

GRID_20_PILOTOS = [
    ("VER", "Max Verstappen", "Red Bull"),
    ("PER", "Sergio Pérez", "Red Bull"),
    ("HAM", "Lewis Hamilton", "Ferrari"),
    ("LEC", "Charles Leclerc", "Ferrari"),
    ("RUS", "George Russell", "Mercedes"),
    ("ANT", "Andrea Kimi Antonelli", "Mercedes"),
    ("NOR", "Lando Norris", "McLaren"),
    ("PIA", "Oscar Piastri", "McLaren"),
    ("ALO", "Fernando Alonso", "Aston Martin"),
    ("STR", "Lance Stroll", "Aston Martin"),
    ("GAS", "Pierre Gasly", "Alpine"),
    ("DOO", "Jack Doohan", "Alpine"),
    ("ALB", "Alexander Albon", "Williams"),
    ("SAI", "Carlos Sainz", "Williams"),
    ("TSU", "Yuki Tsunoda", "RB"),
    ("LAW", "Liam Lawson", "RB"),
    ("HUL", "Nico Hülkenberg", "Kick Sauber"),
    ("BOR", "Gabriel Bortoleto", "Kick Sauber"),
    ("OCO", "Esteban Ocon", "Haas"),
    ("BEA", "Oliver Bearman", "Haas"),
]


def montar_grid_inicial() -> RaceState:
    """Constrói um RaceState de largada com 20 pilotos em grid.

    Todos começam na volta 0, sem gap acumulado, pneu MEDIUM novo,
    tanque cheio e fora do pit. Serve como "estado zero" para os testes
    e, futuramente, como ponto de partida real da simulação.
    """
    drivers = {}
    for grid_position, (driver_id, name, team) in enumerate(GRID_20_PILOTOS, start=1):
        drivers[driver_id] = DriverState(
            driver_id=driver_id,
            name=name,
            team=team,
            position=grid_position,
            current_lap=0,
            last_lap_time=None,
            gap_to_leader=0.0 if grid_position == 1 else float(grid_position - 1) * 0.3,
            gap_to_ahead=None if grid_position == 1 else 0.3,
            tyre_compound=TyreCompound.MEDIUM,
            tyre_age=0,
            fuel_load=110.0,
            pit_status=PitStatus.NONE,
            pit_stops_made=0,
            is_retired=False,
            total_race_time=0.0,
            base_lap_time=90.0 + grid_position * 0.1,  # Tempo base de volta, em segundos
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
    parser = argparse.ArgumentParser(
        description="Roda a simulação"
    )

    # 2. Voltas
    parser.add_argument(
        "-l", "--laps",
        type=int,
        default=1,
        help="Quantidade de voltas a simular, default = 1"
    )

    # 3. Seed aleatória
    parser.add_argument(
        "-s", "--seed", 
        type=int, 
        default=1, 
        help="Seed para a geração de números aleatórios (default: 1)"
    )
    args = parser.parse_args()
    random.seed(args.seed)
    race_state = montar_grid_inicial()
    for _i in range(args.laps):
        tick(race_state, delta_time=1.0)


if __name__ == "__main__":
    main()
