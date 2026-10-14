"""Mede quanto custa gravar uma corrida inteira no banco, volta a volta.

Executar com `make medir`. Cria uma corrida de teste no banco de desenvolvimento
(20 pilotos, 70 voltas), grava cada volta como o motor faria (uma transação por
volta, via `GravadorDeCorrida`), imprime o tempo por volta e apaga a corrida.

O critério do roadmap é "salvar não deixa a simulação perceptivelmente mais lenta".
Para comparar: o guia do M2 emite uma volta a cada 2 s em 1x (0,2 s em 10x).
Não vira teste do CI de propósito: teste de tempo é instável em máquina compartilhada.
"""

import asyncio
import statistics
import time

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.persistencia import GravadorDeCorrida
from db.base import criar_engine
from db.models import Race
from db.repositorio import InscricaoNoGrid, criar_corrida
from sim.state import LapResult, TyreCompound

CODIGOS = [
    "VER", "NOR", "LEC", "PIA", "SAI", "HAM", "RUS", "PER", "ALO", "STR",
    "TSU", "LAW", "GAS", "OCO", "ALB", "COL", "HUL", "MAG", "BOT", "ZHO",
]  # fmt: skip
VOLTAS = 70
SEGUNDOS_POR_VOLTA_EM_1X = 2.0  # integracao-m2.md: 1x ≈ 2 s por volta


def _volta(codigo: str, posicao: int, numero: int) -> LapResult:
    return LapResult(
        driver_id=codigo, lap_number=numero, lap_time=80.0 + posicao * 0.1, position=posicao,
        gap_to_leader=posicao * 0.8 - 0.8, gap_to_ahead=None if posicao == 1 else 0.8,
        tyre_compound=TyreCompound.MEDIUM, tyre_age=numero, fuel_load=100.0 - numero,
        pit_stop=False, pit_time=None,
    )  # fmt: skip


async def _gravar_corrida(gravador: GravadorDeCorrida) -> list[float]:
    duracoes = []
    for numero in range(1, VOLTAS + 1):
        voltas = [_volta(c, i + 1, numero) for i, c in enumerate(CODIGOS)]
        inicio = time.perf_counter()
        await gravador.registrar_volta(voltas)
        duracoes.append(time.perf_counter() - inicio)
    return duracoes


def main() -> None:
    engine = criar_engine()
    with Session(engine) as s, s.begin():
        grid = [InscricaoNoGrid(c, i + 1) for i, c in enumerate(CODIGOS)]
        race_id = criar_corrida(
            s, circuit_id="monza", seed=0, total_laps=VOLTAS, config={"medicao": True}, grid=grid
        ).id
    try:
        duracoes = asyncio.run(_gravar_corrida(GravadorDeCorrida(engine, race_id)))
    finally:
        with Session(engine) as s, s.begin():
            s.execute(delete(Race).where(Race.id == race_id))  # apaga em cascata
    ms = sorted(d * 1000 for d in duracoes)
    p95 = ms[int(len(ms) * 0.95) - 1]
    print(f"{VOLTAS} voltas x {len(CODIGOS)} pilotos = {VOLTAS * len(CODIGOS)} linhas")
    print(f"por volta: média {statistics.mean(ms):.1f} ms | p95 {p95:.1f} ms | máx {ms[-1]:.1f} ms")
    print(f"primeira volta (inclui o mapa): {duracoes[0] * 1000:.1f} ms")
    print(f"total: {sum(duracoes):.2f} s para a corrida inteira")
    print(
        f"fração do intervalo entre voltas em 1x ({SEGUNDOS_POR_VOLTA_EM_1X:g} s): "
        f"{statistics.mean(ms) / 1000 / SEGUNDOS_POR_VOLTA_EM_1X:.2%}"
    )
    engine.dispose()


if __name__ == "__main__":
    main()
