import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useRaceWebSocket } from "@/hooks/useRaceWebSocket";
import { useRaceStore } from "@/store/raceStore";
import { getRaceDetails } from "@/lib/api";
import { RaceTopBar } from "@/components/RaceTopBar";
import { TimingTower } from "@/components/TimingTower";
import { CircuitCanvas } from "@/components/CircuitCanvas";
import { EventFeed } from "@/components/EventFeed";
import { RaceResultsView } from "@/components/RaceResultsView";
import {
  Trophy,
  ArrowLeft,
  RefreshCw,
  AlertCircle,
  LayoutGrid,
  Maximize2,
  Table,
  BarChart2,
  X,
} from "lucide-react";
import { TYRE_INFO, formatGap } from "@/lib/constants";

type ViewMode = "split" | "track-only" | "tower-only" | "results";

export const CockpitScreen: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const raceId = id || "live";

  const {
    togglePause,
    changeSpeed,
    restart,
  } = useRaceWebSocket(raceId);

  const {
    config,
    drivers,
    currentLapData,
    isFinished,
    connectionStatus,
    setRaceConfig,
  } = useRaceStore();

  // Sincroniza os detalhes da corrida com o backend caso o usuário dê F5 ou acerte /race/{id} direto
  useEffect(() => {
    if (!raceId || raceId === "live") return;
    let isMounted = true;

    getRaceDetails(raceId)
      .then((data) => {
        if (!isMounted) return;
        setRaceConfig({
          circuitId: data.circuit_id,
          totalLaps: data.total_laps,
        });
      })
      .catch((err) => {
        console.warn(`[CockpitScreen] Não foi possível carregar detalhes da corrida ${raceId}:`, err);
      });

    return () => {
      isMounted = false;
    };
  }, [raceId, setRaceConfig]);

  const [viewMode, setViewMode] = useState<ViewMode>("split");
  const [selectedDriverId, setSelectedDriverId] = useState<string | null>(null);
  const [showResultsModal, setShowResultsModal] = useState<boolean>(false);

  const leader = drivers[0];
  const selectedDriver = drivers.find((d) => d.driver_id === selectedDriverId) || null;

  return (
    <div className="min-h-screen bg-f1-dark text-slate-100 flex flex-col font-sans">
      {/* Top Bar Oficial com Controles de Simulação */}
      <RaceTopBar
        onTogglePause={togglePause}
        onChangeSpeed={changeSpeed}
        onRestart={() => restart(config.totalLaps, config.circuitId)}
      />

      {/* Alerta de Desconexão */}
      {connectionStatus === "disconnected" && (
        <div className="bg-rose-950/80 border-b border-rose-800 text-rose-300 px-4 py-2 text-xs font-mono flex items-center justify-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400" />
          <span>
            Aviso: Conexão com o servidor de simulação perdida. Tentando reconectar automaticamente...
          </span>
        </div>
      )}

      {/* Faixa de Corrida Finalizada */}
      {isFinished && leader && (
        <div className="bg-gradient-to-r from-amber-600/30 via-amber-500/20 to-amber-600/30 border-b border-amber-500/50 py-3 px-4 shadow-inner">
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Trophy className="w-6 h-6 text-amber-400 animate-bounce" />
              <div>
                <h3 className="font-mono font-bold text-white uppercase text-sm">
                  BANDEIRA QUADRICULADA! VITÓRIA DE {leader.name} ({leader.driver_id})
                </h3>
                <p className="text-xs text-amber-200/80 font-mono">
                  {config.circuitName} • {config.totalLaps} voltas completadas
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowResultsModal(true)}
                className="px-4 py-1.5 rounded bg-amber-500 hover:bg-amber-600 text-black font-mono text-xs font-bold transition-all shadow"
              >
                Ver Classificação Oficial
              </button>
              <Link
                to="/setup"
                className="px-4 py-1.5 rounded bg-f1-red hover:bg-red-700 text-white font-mono text-xs font-bold transition-all shadow"
              >
                Nova Corrida
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Barra de Modos de Visualização e Telemetria de Piloto */}
      <div className="border-b border-f1-border bg-f1-surface/70 px-4 py-2">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
          {/* Seletor de Modos de Exibição */}
          <div className="flex items-center gap-1.5 font-mono text-xs">
            <button
              type="button"
              onClick={() => setViewMode("split")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all ${
                viewMode === "split"
                  ? "bg-f1-red text-white border-f1-red shadow"
                  : "bg-f1-card text-f1-muted border-f1-border hover:text-white"
              }`}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span>Circuito & Torre</span>
            </button>

            <button
              type="button"
              onClick={() => setViewMode("track-only")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all ${
                viewMode === "track-only"
                  ? "bg-f1-red text-white border-f1-red shadow"
                  : "bg-f1-card text-f1-muted border-f1-border hover:text-white"
              }`}
            >
              <Maximize2 className="w-3.5 h-3.5" />
              <span>Pista Cheia</span>
            </button>

            <button
              type="button"
              onClick={() => setViewMode("tower-only")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all ${
                viewMode === "tower-only"
                  ? "bg-f1-red text-white border-f1-red shadow"
                  : "bg-f1-card text-f1-muted border-f1-border hover:text-white"
              }`}
            >
              <Table className="w-3.5 h-3.5" />
              <span>Torre Completa</span>
            </button>

            <button
              type="button"
              onClick={() => setShowResultsModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border bg-f1-card text-amber-300 border-amber-500/40 hover:bg-amber-500/10 transition-all ml-1"
            >
              <BarChart2 className="w-3.5 h-3.5" />
              <span>Resultados / Classificação</span>
            </button>
          </div>

          {/* Card Rápido de Foco no Piloto Selecionado */}
          {selectedDriver && (
            <div className="flex items-center gap-3 bg-f1-dark border border-slate-700 px-3 py-1 rounded-lg text-xs font-mono">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: selectedDriver.teamColor }}
              />
              <span className="font-bold text-white">
                P{selectedDriver.position} • {selectedDriver.driver_id} ({selectedDriver.name})
              </span>
              <span className="text-f1-muted">{selectedDriver.team}</span>
              <span className="text-amber-400 font-bold">{formatGap(selectedDriver.gap_to_leader)}</span>
              <div className="flex items-center gap-1">
                <span
                  className="px-1 rounded text-[10px]"
                  style={{
                    backgroundColor:
                      TYRE_INFO[selectedDriver.tyre_compound]?.color + "33",
                    color: TYRE_INFO[selectedDriver.tyre_compound]?.color,
                  }}
                >
                  {selectedDriver.tyre_compound[0]}
                </span>
                <span className="text-f1-muted text-[10px]">{selectedDriver.tyre_age}v</span>
              </div>
              <button
                onClick={() => setSelectedDriverId(null)}
                className="text-f1-muted hover:text-white ml-1"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Conteúdo Principal do Cockpit */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 flex flex-col gap-4">
        {/* MODO 1: SPLIT (Circuito 2D Hero + Coluna Lateral com Timing Tower e Feed) */}
        {viewMode === "split" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-[calc(100vh-190px)]">
            {/* Coluna Esquerda/Centro: PISTA DE CORRIDA 2D CANVAS (7 de 12 colunas) */}
            <section className="lg:col-span-7 flex flex-col h-full min-h-[460px]">
              <CircuitCanvas
                circuitId={config.circuitId}
                circuitName={config.circuitName}
                drivers={drivers}
                trackStatus={currentLapData?.track_status || "GREEN"}
                selectedDriverId={selectedDriverId}
                onSelectDriver={setSelectedDriverId}
                className="flex-1"
              />
            </section>

            {/* Coluna Direita: Timing Tower Oficial e Feed de Eventos (5 de 12 colunas) */}
            <section className="lg:col-span-5 flex flex-col gap-4 h-full">
              {/* Timing Tower Compacto/Integrado */}
              <div className="flex-1 min-h-[300px]">
                <TimingTower
                  selectedDriverId={selectedDriverId}
                  onSelectDriver={setSelectedDriverId}
                  compact={true}
                />
              </div>

              {/* Feed de Eventos da Direção de Prova */}
              <div className="h-[220px]">
                <EventFeed />
              </div>
            </section>
          </div>
        )}

        {/* MODO 2: PISTA CHEIA (Circuito 2D em 100% de largura) */}
        {viewMode === "track-only" && (
          <div className="flex-1 min-h-[calc(100vh-190px)] flex flex-col">
            <CircuitCanvas
              circuitId={config.circuitId}
              circuitName={config.circuitName}
              drivers={drivers}
              trackStatus={currentLapData?.track_status || "GREEN"}
              selectedDriverId={selectedDriverId}
              onSelectDriver={setSelectedDriverId}
              className="flex-1"
            />
          </div>
        )}

        {/* MODO 3: TORRE COMPLETA (Visualização tabular detalhada de tempos) */}
        {viewMode === "tower-only" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-[calc(100vh-190px)]">
            <section className="lg:col-span-8 flex flex-col h-full">
              <TimingTower
                selectedDriverId={selectedDriverId}
                onSelectDriver={setSelectedDriverId}
                compact={false}
              />
            </section>
            <section className="lg:col-span-4 flex flex-col gap-4 h-full">
              {/* Resumo da Corrida */}
              <div className="bg-f1-surface border border-f1-border rounded-xl p-4 shadow-xl font-mono text-xs">
                <div className="flex items-center justify-between pb-3 border-b border-f1-border/60">
                  <span className="text-f1-muted uppercase font-bold text-[11px]">
                    Líder da Prova
                  </span>
                  <span className="text-amber-400 font-bold">
                    {leader ? `${leader.position}º • ${leader.driver_id}` : "-"}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-3 text-slate-300">
                  <div>
                    <span className="text-f1-muted block text-[10px] uppercase">
                      Circuito
                    </span>
                    <span className="font-semibold">{config.circuitId}</span>
                  </div>
                  <div>
                    <span className="text-f1-muted block text-[10px] uppercase">
                      Seed
                    </span>
                    <span className="font-semibold">{config.seed}</span>
                  </div>
                  <div>
                    <span className="text-f1-muted block text-[10px] uppercase">
                      Pneu do Líder
                    </span>
                    <span className="font-semibold">
                      {leader?.tyre_compound} ({leader?.tyre_age}v)
                    </span>
                  </div>
                  <div>
                    <span className="text-f1-muted block text-[10px] uppercase">
                      Combustível
                    </span>
                    <span className="font-semibold">
                      {leader ? `${leader.fuel_load_kg.toFixed(0)} kg` : "-"}
                    </span>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-f1-border/60 flex items-center justify-between">
                  <Link
                    to="/setup"
                    className="flex items-center gap-1.5 text-xs text-f1-muted hover:text-white transition-colors"
                  >
                    <ArrowLeft className="w-3.5 h-3.5" />
                    Configuração
                  </Link>
                  <button
                    type="button"
                    onClick={() => restart(config.totalLaps, config.circuitId)}
                    className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300 transition-colors"
                  >
                    <RefreshCw className="w-3 h-3" />
                    Reiniciar
                  </button>
                </div>
              </div>

              <div className="flex-1 overflow-hidden">
                <EventFeed />
              </div>
            </section>
          </div>
        )}
      </main>

      {/* Modal / Overlay de Resultados Oficiais */}
      {showResultsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-4xl max-h-[92vh] overflow-hidden">
            <RaceResultsView
              raceId={raceId}
              circuitId={config.circuitId}
              circuitName={config.circuitName}
              totalLaps={config.totalLaps}
              fallbackDrivers={drivers}
              onRestart={() => {
                setShowResultsModal(false);
                restart(config.totalLaps, config.circuitId);
              }}
              onClose={() => setShowResultsModal(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
};
