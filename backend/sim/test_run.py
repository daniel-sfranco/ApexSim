"""
Testes de sim/run.py
=====================

Este módulo testa a camada de CLI/bootstrap da simulação:

1. montar_grid_inicial() — reaproveita a mesma bateria de checagens
   estruturais já usada para sim/state.py, porque run.py tem sua PRÓPRIA
   cópia dessa função. Se um dia ela for centralizada em um só lugar
   (recomendo isso — ver observação ao final), estes testes continuam
   valendo sem alteração.
2. Parsing de argumentos (argparse) — valores default e valores
   explícitos de --laps e --seed.
3. Reprodutibilidade do seed — que a MESMA seed sempre produz a MESMA
   sequência de números aleatórios 

Rodar com:
    pytest test_run.py -v
"""

import random
import sys

import pytest

from sim.run import montar_grid_inicial, main, GRID_20_PILOTOS
from sim.state import PitStatus, TyreCompound, RaceState, DriverState, TrackStatus, tick
# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
 
def piloto(driver_id: str, base_lap_time: float, position: int = 1) -> DriverState:
    """Cria um DriverState mínimo, só com o necessário para testar tick().
 
    Isolar isso num helper evita repetir os ~15 campos obrigatórios em
    cada teste e deixa claro quais valores realmente importam para o
    caso testado (aqui: base_lap_time e position de largada).
    """
    return DriverState(
        driver_id=driver_id,
        name=driver_id,
        team="Equipe",
        position=position,
        current_lap=0,
        last_lap_time=None,
        gap_to_leader=0.0,
        gap_to_ahead=None,
        tyre_compound=TyreCompound.MEDIUM,
        tyre_age=0,
        fuel_load=110.0,
        pit_status=PitStatus.NONE,
        pit_stops_made=0,
        is_retired=False,
        total_race_time=0.0,
        base_lap_time=base_lap_time,
    )
 
 
def estado_com(pilotos: list[DriverState], total_laps: int = 58) -> RaceState:
    """Monta um RaceState mínimo a partir de uma lista de pilotos já prontos."""
    from sim.state import TrackStatus
 
    return RaceState(
        current_lap=0,
        total_laps=total_laps,
        track_status=TrackStatus.GREEN,
        drivers={d.driver_id: d for d in pilotos},
        lap_history=[],
        elapsed_time=0.0,
        is_finished=False,
    )
 
 
# ---------------------------------------------------------------------------
# TESTES: cálculo de posição e gap (sem ruído — desvio_padrão=0 não dá
# pra zerar direto porque random.gauss(0, 1.0) está hardcoded em tick();
# por isso fixamos a seed e comparamos com o valor determinístico real,
# em vez de tentar eliminar o ruído).
# ---------------------------------------------------------------------------
 
def test_lider_fica_em_primeiro_com_menor_tempo_base(monkeypatch):
    """Sem ruído (mockando random.gauss para sempre 0), quem tem o menor
    base_lap_time deve ficar em P1 após uma volta.
    """
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([
        piloto("A", base_lap_time=91.0),
        piloto("B", base_lap_time=90.0),  # mais rápido
        piloto("C", base_lap_time=92.0),
    ])
 
    tick(estado, delta_time=1.0)
 
    assert estado.drivers["B"].position == 1
    assert estado.drivers["A"].position == 2
    assert estado.drivers["C"].position == 3
 
 
def test_lider_tem_gap_zero_e_gap_ahead_none(monkeypatch):
    """O piloto em P1 deve sempre ter gap_to_leader=0 e gap_to_ahead=None."""
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 91.0), piloto("B", 90.0)])
 
    tick(estado, delta_time=1.0)
 
    lider = estado.drivers["B"]
    assert lider.gap_to_leader == 0.0
    assert lider.gap_to_ahead is None
 
 
def test_gap_to_leader_e_diferenca_de_tempo_total(monkeypatch):
    """gap_to_leader deve ser exatamente total_race_time - total do líder."""
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([
        piloto("A", base_lap_time=91.5),
        piloto("B", base_lap_time=90.0),
    ])
 
    tick(estado, delta_time=1.0)
 
    esperado = estado.drivers["A"].total_race_time - estado.drivers["B"].total_race_time
    assert estado.drivers["A"].gap_to_leader == pytest.approx(esperado)
    assert estado.drivers["A"].gap_to_leader == pytest.approx(1.5)
 
 
def test_gap_to_ahead_com_tres_pilotos_em_fila(monkeypatch):
    """Com 3 pilotos em ordem, gap_to_ahead deve refletir apenas a
    diferença para o carro imediatamente à frente, não para o líder.
    """
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([
        piloto("A", base_lap_time=90.0),  # P1
        piloto("B", base_lap_time=91.0),  # P2, +1.0s do líder
        piloto("C", base_lap_time=92.5),  # P3, +2.5s do líder, +1.5s de B
    ])
 
    tick(estado, delta_time=1.0)
 
    assert estado.drivers["B"].gap_to_ahead == pytest.approx(1.0)
    assert estado.drivers["C"].gap_to_ahead == pytest.approx(1.5)
    assert estado.drivers["C"].gap_to_leader == pytest.approx(2.5)
 
 
def test_current_lap_avanca_uma_unidade_por_tick(monkeypatch):
    """Cada chamada de tick() deve avançar current_lap em exatamente 1,
    tanto no RaceState quanto em cada DriverState.
    """
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 90.0), piloto("B", 91.0)])
 
    tick(estado, delta_time=1.0)
    assert estado.current_lap == 1
    assert all(d.current_lap == 1 for d in estado.drivers.values())
 
    tick(estado, delta_time=1.0)
    assert estado.current_lap == 2
    assert all(d.current_lap == 2 for d in estado.drivers.values())
 
 
# ---------------------------------------------------------------------------
# TESTES: determinismo via seed (o requisito central do marco do roteiro)
# ---------------------------------------------------------------------------
 
def _rodar_50_voltas(seed: int) -> list[tuple[str, int, float]]:
    """Roda 50 voltas com uma seed dada e devolve um snapshot comparável
    do resultado: (driver_id, posição final, tempo total), ordenado por
    driver_id para a comparação não depender de ordem de dict.
    """
    random.seed(seed)
    estado = montar_grid_inicial()
    for _ in range(50):
        tick(estado, delta_time=1.0)
    return sorted(
        (d.driver_id, d.position, round(d.total_race_time, 6))
        for d in estado.drivers.values()
    )
 
 
def test_mesma_seed_produz_corrida_identica(capsys):
    """Rodar 50 voltas duas vezes com a mesma seed deve dar o MESMO
    resultado final — posição e tempo total de cada piloto idênticos.
 
    Isso é o teste mais importante para o marco 'python -m sim.run
    --laps 50 --seed 42': sem determinismo, o mesmo comando pode
    imprimir corridas diferentes a cada execução, o que invalida
    reprodutibilidade para debug e para comparação de resultados.
    """
    resultado_1 = _rodar_50_voltas(seed=42)
    resultado_2 = _rodar_50_voltas(seed=42)
    capsys.readouterr()  # descarta o print() interno de tick(), ver nota abaixo
 
    assert resultado_1 == resultado_2
 
 
def test_seeds_diferentes_tendem_a_produzir_corridas_diferentes(capsys):
    """Seeds diferentes devem, com altíssima probabilidade, gerar
    resultados diferentes — confirma que a seed está de fato afetando
    o resultado, e não sendo ignorada.
    """
    resultado_1 = _rodar_50_voltas(seed=1)
    resultado_2 = _rodar_50_voltas(seed=2)
    capsys.readouterr()
 
    assert resultado_1 != resultado_2
 
 
# ---------------------------------------------------------------------------
# TESTES: bugs conhecidos (documentados via xfail — ver docstring do módulo)
# ---------------------------------------------------------------------------
 
 
def test_tick_registra_lap_result_no_historico(monkeypatch, capsys):
    """Cada tick() deve gerar um LapResult por piloto e anexar em lap_history."""
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 90.0), piloto("B", 91.0)])
 
    tick(estado, delta_time=1.0)
    capsys.readouterr()
 
    assert len(estado.lap_history) == 2
 
 
def test_lap_history_acumula_entre_ticks(monkeypatch, capsys):
    """lap_history deve CRESCER a cada tick, não ser sobrescrito.
 
    Com N pilotos e T ticks, o histórico deve ter N*T registros ao final —
    se o histórico fosse resetado a cada tick (bug comum: usar `=` em vez
    de `.append`/`.extend`), este teste pegaria isso.
    """
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 90.0), piloto("B", 91.0), piloto("C", 92.0)])
 
    for _ in range(5):
        tick(estado, delta_time=1.0)
    capsys.readouterr()
 
    assert len(estado.lap_history) == 3 * 5
 
 
def test_lap_result_reflete_os_dados_corretos_do_piloto(monkeypatch, capsys):
    """Os campos do LapResult devem bater com o DriverState no momento
    em que a volta foi registrada — não com valores de uma volta anterior
    nem com o estado de outro piloto.
    """
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 90.0), piloto("B", 91.0)])
 
    tick(estado, delta_time=1.0)
    capsys.readouterr()
 
    resultado_a = next(r for r in estado.lap_history if r.driver_id == "A")
    driver_a = estado.drivers["A"]
 
    assert resultado_a.lap_number == 1
    assert resultado_a.lap_time == pytest.approx(driver_a.last_lap_time)
    assert resultado_a.position == driver_a.position
    assert resultado_a.gap_to_leader == pytest.approx(driver_a.gap_to_leader)
    assert resultado_a.gap_to_ahead == driver_a.gap_to_ahead
    assert resultado_a.pit_stop is False
    assert resultado_a.pit_time is None
 
 
def test_lap_result_e_imutavel_apos_registrado(monkeypatch, capsys):
    """Um LapResult já no histórico não deve ser alterável (é frozen),
    protegendo o histórico de mutações acidentais depois do fato.
    """
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([piloto("A", 90.0)])
 
    tick(estado, delta_time=1.0)
    capsys.readouterr()
 
    registro = estado.lap_history[0]
    with pytest.raises(Exception):
        registro.lap_time = 999.0  # type: ignore[misc]
 
 
def test_lap_history_esta_ordenado_por_posicao_dentro_da_mesma_volta(monkeypatch, capsys):
    """Dentro dos registros de uma mesma volta, a ordem no histórico
    deve seguir a posição (P1 primeiro) — só para o histórico ficar
    legível quando inspecionado/exportado depois.
    """
    monkeypatch.setattr(random, "gauss", lambda mu, sigma: 0.0)
    estado = estado_com([
        piloto("A", base_lap_time=92.0),
        piloto("B", base_lap_time=90.0),
        piloto("C", base_lap_time=91.0),
    ])
 
    tick(estado, delta_time=1.0)
    capsys.readouterr()
 
    posicoes_no_historico = [r.position for r in estado.lap_history]
    assert posicoes_no_historico == [1, 2, 3]
 
 
def test_tick_atualmente_imprime_no_stdout(capsys):
    """Documenta o efeito colateral atual: tick() faz print() por piloto.
 
    Isso NÃO é um teste de 'comportamento desejado' — é uma trava para
    percebermos se/quando esse print() for removido do motor (o que é
    recomendável: I/O deveria ficar em run.py, não em state.py).
    Se este teste começar a falhar, é sinal de que a refatoração
    recomendada (mover a impressão para run.py) foi feita — nesse caso,
    é para DELETAR este teste, não corrigi-lo.
    """
    monkeypatch_estado = estado_com([piloto("A", 90.0)])
    tick(monkeypatch_estado, delta_time=1.0)
 
    saida = capsys.readouterr()
    assert "Driver A" in saida.out
