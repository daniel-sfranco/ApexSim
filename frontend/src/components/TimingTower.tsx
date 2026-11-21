import React from "react";
import { useRaceStore } from "@/store/raceStore";
import {
  TYRE_INFO,
  formatLapTime,
  formatGap,
} from "@/lib/constants";
import { ChevronUp, ChevronDown, Minus, Fuel } from "lucide-react";

interface TimingTowerProps {
  selectedDriverId?: string | null;
  onSelectDriver?: (driverId: string | null) => void;
  compact?: boolean;
}

export const TimingTower: React.FC<TimingTowerProps> = ({
  selectedDriverId,
  onSelectDriver,
  compact = false,
}) => {
  const { drivers } = useRaceStore();

  return (
    <div className="bg-f1-surface border border-f1-border rounded-xl shadow-xl overflow-hidden flex flex-col h-full">
      {/* Cabeçalho da Torre */}
      <div className="bg-f1-dark/95 px-4 py-2.5 border-b border-f1-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-f1-red animate-pulse"></span>
          <span className="text-xs font-mono font-bold tracking-wider uppercase text-white">
            Timing Tower Oficial
          </span>
        </div>
        <span className="text-[11px] font-mono text-f1-muted">
          {drivers.length} Pilotos
        </span>
      </div>

      {/* Grid de Colunas */}
      <div className="grid grid-cols-12 gap-1 px-3 py-2 bg-f1-card text-[11px] font-mono text-f1-muted uppercase border-b border-f1-border font-semibold select-none">
        <div className="col-span-1 text-center">POS</div>
        <div className={compact ? "col-span-4" : "col-span-3"}>PILOTO</div>
        <div className={compact ? "col-span-3 text-right" : "col-span-2 text-right"}>
          GAP LÍDER
        </div>
        {!compact && <div className="col-span-2 text-right">INT</div>}
        <div className={compact ? "col-span-2 text-right" : "col-span-2 text-right"}>
          {compact ? "VOLTA" : "ÚLTIMA VOLTA"}
        </div>
        <div className="col-span-2 text-center">PNEU</div>
      </div>

      {/* Linhas dos Pilotos */}
      <div className="divide-y divide-f1-border/40 overflow-y-auto flex-1 font-mono">
        {drivers.map((driver) => {
          const tyre = TYRE_INFO[driver.tyre_compound] || TYRE_INFO.UNKNOWN;
          const isLeader = driver.position === 1;
          const isInPoints = driver.position <= 10;
          const isPodium = driver.position <= 3;
          const inPit = driver.pit_status && driver.pit_status !== "NONE";
          const isSelected = selectedDriverId === driver.driver_id;

          return (
            <div
              key={driver.driver_id}
              onClick={() => onSelectDriver?.(isSelected ? null : driver.driver_id)}
              className={`grid grid-cols-12 gap-1 items-center px-3 py-1.5 text-xs cursor-pointer transition-all duration-150 ${
                isSelected
                  ? "bg-slate-700/60 ring-1 ring-white/60"
                  : driver.positionChange > 0
                  ? "bg-emerald-950/20 hover:bg-emerald-900/30"
                  : driver.positionChange < 0
                  ? "bg-rose-950/20 hover:bg-rose-900/30"
                  : "hover:bg-f1-card/70"
              }`}
            >
              {/* POSIÇÃO E INDICADOR DE ULTRAPASSAGEM */}
              <div className="col-span-1 flex items-center justify-center gap-0.5">
                <span
                  className={`font-bold w-4 text-center ${
                    isPodium
                      ? driver.position === 1
                        ? "text-amber-400 font-extrabold"
                        : driver.position === 2
                        ? "text-slate-300"
                        : "text-amber-600"
                      : isInPoints
                      ? "text-white"
                      : "text-f1-muted"
                  }`}
                >
                  {driver.position}
                </span>

                {/* Variação de Posição */}
                <span className="w-2.5 flex justify-center">
                  {driver.positionChange > 0 ? (
                    <ChevronUp className="w-3 h-3 text-emerald-400 font-bold" />
                  ) : driver.positionChange < 0 ? (
                    <ChevronDown className="w-3 h-3 text-rose-400 font-bold" />
                  ) : (
                    <Minus className="w-2 h-2 text-f1-border" />
                  )}
                </span>
              </div>

              {/* IDENTIFICAÇÃO DO PILOTO E EQUIPE */}
              <div
                className={`${
                  compact ? "col-span-4" : "col-span-3"
                } flex items-center gap-1.5 overflow-hidden`}
              >
                {/* Faixa Colorida da Equipe */}
                <div
                  className="w-1 h-4.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: driver.teamColor }}
                />

                <div className="truncate">
                  <div className="flex items-center gap-1">
                    <span className="font-bold text-white tracking-wide text-xs">
                      {driver.driver_id}
                    </span>
                    {driver.drs_active && (
                      <span className="text-[8px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 px-0.5 rounded font-bold">
                        DRS
                      </span>
                    )}
                  </div>
                  {!compact && (
                    <div className="text-[9px] text-f1-muted truncate">
                      {driver.name}
                    </div>
                  )}
                </div>
              </div>

              {/* GAP PARA O LÍDER */}
              <div
                className={`${
                  compact ? "col-span-3" : "col-span-2"
                } text-right`}
              >
                <span
                  className={`font-semibold ${
                    isLeader ? "text-amber-400 font-bold" : "text-slate-300"
                  }`}
                >
                  {isLeader ? "LÍDER" : formatGap(driver.gap_to_leader)}
                </span>
              </div>

              {/* GAP PARA O CARRO À FRENTE (INTERVALO) */}
              {!compact && (
                <div className="col-span-2 text-right text-f1-muted">
                  {isLeader ? "-" : formatGap(driver.gap_to_ahead)}
                </div>
              )}

              {/* ÚLTIMA VOLTA */}
              <div
                className={`${
                  compact ? "col-span-2" : "col-span-2"
                } text-right`}
              >
                <span
                  className={
                    driver.last_lap_time &&
                    driver.bestLapTime &&
                    driver.last_lap_time <= driver.bestLapTime
                      ? "text-purple-400 font-bold"
                      : "text-slate-200"
                  }
                >
                  {formatLapTime(driver.last_lap_time)}
                </span>
                {!compact && (
                  <div className="flex items-center justify-end gap-1 text-[9px] text-f1-muted">
                    <Fuel className="w-2.5 h-2.5" />
                    <span>{driver.fuel_load_kg.toFixed(0)}kg</span>
                  </div>
                )}
              </div>

              {/* PNEU / IDADE / PIT */}
              <div className="col-span-2 flex items-center justify-center gap-1">
                {inPit ? (
                  <span className="bg-amber-500 text-black font-extrabold text-[9px] px-1 py-0.2 rounded animate-pulse">
                    PIT
                  </span>
                ) : (
                  <>
                    <span
                      className={`inline-flex items-center justify-center w-4.5 h-4.5 rounded-full border text-[9px] font-bold ${tyre.border} ${tyre.bg}`}
                      style={{ color: tyre.color }}
                      title={`${tyre.label} (${driver.tyre_age} voltas)`}
                    >
                      {tyre.letter}
                    </span>
                    <span className="text-[10px] text-f1-muted font-medium">
                      {driver.tyre_age}v
                    </span>
                  </>
                )}

                {driver.pit_stops_made > 0 && (
                  <span className="text-[9px] text-f1-muted font-semibold bg-f1-border/50 px-1 rounded">
                    {driver.pit_stops_made}P
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
