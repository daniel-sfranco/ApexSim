import React from "react";
import { Link, useParams } from "react-router-dom";
import { useRaceWebSocket } from "@/hooks/useRaceWebSocket";
import { useRaceStore } from "@/store/raceStore";
import { RaceTopBar } from "@/components/RaceTopBar";
import { TimingTower } from "@/components/TimingTower";
import { EventFeed } from "@/components/EventFeed";
import { Trophy, ArrowLeft, RefreshCw, AlertCircle } from "lucide-react";

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
    isFinished,
    connectionStatus,
  } = useRaceStore();

  const leader = drivers[0];

  return (
    <div className="min-h-screen bg-f1-dark text-slate-100 flex flex-col font-sans">
      {/* Top Bar com Controles e Status da Prova */}
      <RaceTopBar
        onTogglePause={togglePause}
        onChangeSpeed={changeSpeed}
        onRestart={() => restart(config.totalLaps, config.circuitId)}
      />

      {/* Alerta de Desconexão (Requisito do Roadmap) */}
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
          <div className="max-w-7xl mx-auto flex items-center justify-between">
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

            <Link
              to="/setup"
              className="px-4 py-1.5 rounded bg-f1-red hover:bg-red-700 text-white font-mono text-xs font-bold transition-all shadow"
            >
              Nova Corrida
            </Link>
          </div>
        </div>
      )}

      {/* Conteúdo Principal: Cockpit em Grid */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Coluna Esquerda: Timing Tower Oficial (8 de 12 colunas no desktop) */}
        <section className="lg:col-span-8 flex flex-col h-[calc(100vh-140px)]">
          <TimingTower />
        </section>

        {/* Coluna Direita: Direção de Prova e Resumo (4 de 12 colunas no desktop) */}
        <section className="lg:col-span-4 flex flex-col gap-4 h-[calc(100vh-140px)]">
          {/* Card de Resumo Rápido da Prova */}
          <div className="bg-f1-surface border border-f1-border rounded-lg p-4 shadow-xl font-mono text-xs">
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
                Configurar Corrida
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

          {/* Feed da Direção de Prova */}
          <div className="flex-1 overflow-hidden">
            <EventFeed />
          </div>
        </section>
      </main>
    </div>
  );
};
