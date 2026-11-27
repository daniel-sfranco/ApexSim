import React from "react";
import { Link } from "react-router-dom";
import { useRaceStore } from "@/store/raceStore";
import { TRACK_STATUS_CONFIG } from "@/lib/constants";
import { Play, Pause, RotateCcw, Activity, CloudSun, ArrowLeft } from "lucide-react";

interface RaceTopBarProps {
  onTogglePause: () => void;
  onChangeSpeed: (speed: number) => void;
  onRestart: () => void;
}

export const RaceTopBar: React.FC<RaceTopBarProps> = ({
  onTogglePause,
  onChangeSpeed,
  onRestart,
}) => {
  const {
    config,
    currentLapData,
    isPaused,
    speedMultiplier,
    connectionStatus,
    isFinished,
  } = useRaceStore();

  const currentLap = currentLapData?.current_lap ?? 0;
  const totalLaps = currentLapData?.total_laps ?? config.totalLaps;
  const trackStatus = currentLapData?.track_status ?? "GREEN";
  const weather = currentLapData?.weather ?? config.weather;
  const trackTemp = currentLapData?.track_temp ?? config.trackTemp;

  const statusConfig = TRACK_STATUS_CONFIG[trackStatus] || TRACK_STATUS_CONFIG.GREEN;

  const speedOptions = [1, 2, 5, 10];

  return (
    <header className="bg-f1-surface border-b border-f1-border px-4 py-3 sticky top-0 z-40 shadow-lg">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        {/* Lado Esquerdo: Voltar, Identificação do GP e Voltas */}
        <div className="flex items-center gap-4">
          <Link
            to="/setup"
            title="Voltar para Configuração"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-f1-card hover:bg-f1-border border border-f1-border text-xs font-mono text-slate-300 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Setup</span>
          </Link>

          <div className="flex items-center gap-2">
            <span className="w-2.5 h-7 bg-f1-red rounded-sm"></span>
            <div>
              <h1 className="text-lg font-bold text-white tracking-wider uppercase font-mono">
                {config.circuitName}
              </h1>
              <p className="text-xs text-f1-muted">ApexSim • Cockpit de Telemetria</p>
            </div>
          </div>

          <div className="h-8 w-px bg-f1-border hidden sm:block"></div>

          {/* Contador de Voltas */}
          <div className="bg-f1-dark px-3 py-1.5 rounded border border-f1-border flex items-baseline gap-1.5">
            <span className="text-xs uppercase font-medium text-f1-muted">Volta</span>
            <span className="text-lg font-mono font-bold text-white">
              {currentLap}
            </span>
            <span className="text-xs font-mono text-f1-muted">/ {totalLaps}</span>
            {isFinished && (
              <span className="ml-2 text-xs bg-f1-red text-white font-bold px-1.5 py-0.5 rounded animate-pulse">
                FINALIZADA
              </span>
            )}
          </div>

          {/* Badge de Status da Pista */}
          <div
            className={`px-3 py-1 rounded border text-xs font-mono font-bold tracking-wider flex items-center gap-2 ${
              statusConfig.bg
            } ${statusConfig.text} ${statusConfig.border} ${
              statusConfig.pulse ? "animate-pulse" : ""
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-current"></span>
            {statusConfig.label}
          </div>
        </div>

        {/* Lado Direito: Clima, Velocidade e Controles */}
        <div className="flex items-center flex-wrap gap-3">
          {/* Condição Climática */}
          <div className="flex items-center gap-1.5 bg-f1-dark/80 px-2.5 py-1.5 rounded border border-f1-border text-xs text-slate-300 font-mono">
            <CloudSun className="w-4 h-4 text-amber-400" />
            <span>{weather === "DRY" ? "Seco" : weather === "DAMP" ? "Úmido" : "Chuva"}</span>
            <span className="text-f1-muted">•</span>
            <span>{trackTemp}°C</span>
          </div>

          {/* Seletor de Velocidade */}
          <div className="flex items-center bg-f1-dark rounded border border-f1-border p-0.5">
            {speedOptions.map((speed) => (
              <button
                key={speed}
                onClick={() => onChangeSpeed(speed)}
                className={`px-2 py-1 text-xs font-mono font-semibold rounded transition-colors ${
                  speedMultiplier === speed
                    ? "bg-f1-red text-white shadow"
                    : "text-f1-muted hover:text-white"
                }`}
                title={`Velocidade ${speed}x`}
              >
                {speed}x
              </button>
            ))}
          </div>

          {/* Botões de Ação */}
          <button
            onClick={onTogglePause}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded font-mono text-xs font-bold transition-all shadow ${
              isPaused
                ? "bg-emerald-600 hover:bg-emerald-500 text-white"
                : "bg-amber-600 hover:bg-amber-500 text-white"
            }`}
          >
            {isPaused ? (
              <>
                <Play className="w-3.5 h-3.5 fill-current" /> RETOMAR
              </>
            ) : (
              <>
                <Pause className="w-3.5 h-3.5 fill-current" /> PAUSAR
              </>
            )}
          </button>

          <button
            onClick={onRestart}
            className="p-1.5 rounded bg-f1-card hover:bg-f1-border text-slate-300 hover:text-white border border-f1-border transition-colors"
            title="Reiniciar Corrida"
          >
            <RotateCcw className="w-4 h-4" />
          </button>

          {/* Indicador de Conexão WebSocket */}
          <div
            className={`flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-mono border ${
              connectionStatus === "connected"
                ? "bg-emerald-950/40 text-emerald-400 border-emerald-800/40"
                : connectionStatus === "connecting"
                ? "bg-amber-950/40 text-amber-400 border-amber-800/40"
                : "bg-rose-950/40 text-rose-400 border-rose-800/40"
            }`}
            title={`WebSocket Status: ${connectionStatus}`}
          >
            <Activity className="w-3 h-3 animate-pulse" />
            <span className="hidden md:inline capitalize">{connectionStatus}</span>
          </div>
        </div>
      </div>
    </header>
  );
};
