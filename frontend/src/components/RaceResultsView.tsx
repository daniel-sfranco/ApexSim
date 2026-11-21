import React, { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { getRaceResults } from "@/lib/api";
import { RaceResultsResponse, DriverFinalResult, EnrichedDriverState } from "@/types";
import { formatLapTime, formatGap } from "@/lib/constants";
import {
  Trophy,
  Medal,
  Flag,
  RotateCcw,
  PlusCircle,
  Clock,
  Wrench,
  AlertCircle,
  X,
} from "lucide-react";

interface RaceResultsViewProps {
  raceId: string;
  circuitId: string;
  circuitName: string;
  totalLaps: number;
  fallbackDrivers: EnrichedDriverState[];
  onRestart?: () => void;
  onClose?: () => void;
}

interface FastestLapRecord {
  driver: string;
  time: number;
}

export const RaceResultsView: React.FC<RaceResultsViewProps> = ({
  raceId,
  circuitId,
  circuitName,
  totalLaps,
  fallbackDrivers,
  onRestart,
  onClose,
}) => {
  const [results, setResults] = useState<RaceResultsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [apiError, setApiError] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    getRaceResults(raceId)
      .then((data) => {
        if (!isMounted) return;
        setResults(data);
        setLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.warn(`[RaceResultsView] Não foi possível carregar resultados da API para ${raceId}:`, err);
        setApiError(true);
        setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [raceId]);

  // Se a API retornou classificação oficial, usamos ela; caso contrário, geramos a partir do fallbackDrivers
  const classification: DriverFinalResult[] =
    results?.classification && results.classification.length > 0
      ? results.classification
      : fallbackDrivers.map((d) => ({
          position: d.position,
          driver_id: d.driver_id,
          name: d.name,
          team: d.team,
          total_race_time: d.last_lap_time ? d.last_lap_time * totalLaps : 0,
          gap_to_leader: d.gap_to_leader,
          pit_stops_made: d.pit_stops_made,
          fastest_lap: d.bestLapTime ?? d.last_lap_time,
          is_retired: d.is_retired,
        }));

  const winner = classification[0];
  const second = classification[1];
  const third = classification[2];

  const overallFastestLap = useMemo<FastestLapRecord | null>(() => {
    let best: FastestLapRecord | null = null;
    for (const d of classification) {
      if (typeof d.fastest_lap === "number") {
        if (!best || d.fastest_lap < best.time) {
          best = { driver: d.driver_id, time: d.fastest_lap };
        }
      }
    }
    return best;
  }, [classification]);

  return (
    <div className="bg-f1-surface border border-f1-border rounded-xl shadow-2xl p-6 font-mono text-white flex flex-col max-h-[90vh] overflow-hidden">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between pb-4 border-b border-f1-border/80">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400">
            <Trophy className="w-6 h-6 animate-bounce" />
          </div>
          <div>
            <h2 className="text-lg font-bold uppercase tracking-wider text-white flex items-center gap-2">
              Classificação Oficial da Corrida
            </h2>
            <p className="text-xs text-f1-muted">
              {circuitName} ({circuitId}) • {totalLaps} Voltas Concluídas
              {results ? " • Validado via API" : " • Telemetria em Tempo Real"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-f1-card hover:bg-f1-border text-f1-muted hover:text-white transition-colors"
              title="Fechar"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Pódio dos 3 Primeiros */}
      {winner && (
        <div className="grid grid-cols-3 gap-3 my-4">
          {/* P2 */}
          <div className="bg-f1-card border border-slate-700/60 rounded-lg p-3 text-center flex flex-col items-center justify-center order-1">
            <Medal className="w-5 h-5 text-slate-300 mb-1" />
            <span className="text-[10px] text-slate-400 uppercase font-bold">2º Lugar</span>
            <span className="font-bold text-sm text-slate-100">{second?.name || second?.driver_id}</span>
            <span className="text-[11px] text-f1-muted">{second?.team}</span>
            <span className="text-xs text-amber-300 font-semibold mt-1">
              {formatGap(second?.gap_to_leader)}
            </span>
          </div>

          {/* P1 - Vencedor */}
          <div className="bg-gradient-to-b from-amber-950/40 to-f1-card border-2 border-amber-500/80 rounded-lg p-4 text-center flex flex-col items-center justify-center order-2 shadow-lg shadow-amber-500/10">
            <Trophy className="w-7 h-7 text-amber-400 mb-1 animate-pulse" />
            <span className="text-xs text-amber-400 uppercase font-extrabold tracking-widest">
              Vencedor
            </span>
            <span className="font-bold text-base text-white">{winner.name || winner.driver_id}</span>
            <span className="text-xs text-amber-200/80 font-medium">{winner.team}</span>
            <span className="text-xs text-emerald-400 font-bold mt-1">
              {winner.total_race_time > 0 ? formatLapTime(winner.total_race_time) : "VENCEDOR"}
            </span>
          </div>

          {/* P3 */}
          <div className="bg-f1-card border border-amber-800/40 rounded-lg p-3 text-center flex flex-col items-center justify-center order-3">
            <Medal className="w-5 h-5 text-amber-600 mb-1" />
            <span className="text-[10px] text-amber-600 uppercase font-bold">3º Lugar</span>
            <span className="font-bold text-sm text-slate-100">{third?.name || third?.driver_id}</span>
            <span className="text-[11px] text-f1-muted">{third?.team}</span>
            <span className="text-xs text-amber-300 font-semibold mt-1">
              {formatGap(third?.gap_to_leader)}
            </span>
          </div>
        </div>
      )}

      {/* Destaque da Volta Mais Rápida */}
      {overallFastestLap && (
        <div className="bg-purple-950/30 border border-purple-800/50 rounded-lg px-3 py-1.5 mb-3 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-purple-300">
            <Clock className="w-3.5 h-3.5 text-purple-400" />
            <span>Volta Mais Rápida da Prova:</span>
            <span className="font-bold text-white">{overallFastestLap.driver}</span>
          </div>
          <span className="font-bold text-purple-300">
            {formatLapTime(overallFastestLap.time)}
          </span>
        </div>
      )}

      {/* Tabela de Classificação Completa */}
      <div className="flex-1 overflow-y-auto border border-f1-border rounded-lg bg-f1-dark/60">
        <div className="grid grid-cols-12 gap-2 px-3 py-2 bg-f1-card text-[11px] font-bold text-f1-muted uppercase border-b border-f1-border sticky top-0 z-10">
          <div className="col-span-1 text-center">POS</div>
          <div className="col-span-4">PILOTO</div>
          <div className="col-span-3">EQUIPE</div>
          <div className="col-span-2 text-right">GAP / TEMPO</div>
          <div className="col-span-2 text-center">PITS / MELHOR</div>
        </div>

        <div className="divide-y divide-f1-border/40 text-xs">
          {classification.map((d) => (
            <div
              key={d.driver_id}
              className={`grid grid-cols-12 gap-2 px-3 py-2 items-center hover:bg-f1-card/60 transition-colors ${
                d.is_retired ? "opacity-60 bg-rose-950/10" : ""
              }`}
            >
              <div className="col-span-1 text-center font-bold">
                {d.is_retired ? (
                  <span className="text-rose-400 text-[10px]">DNF</span>
                ) : (
                  <span
                    className={
                      d.position === 1
                        ? "text-amber-400"
                        : d.position === 2
                        ? "text-slate-300"
                        : d.position === 3
                        ? "text-amber-600"
                        : "text-white"
                    }
                  >
                    {d.position}
                  </span>
                )}
              </div>

              <div className="col-span-4 flex items-center gap-2 overflow-hidden">
                <span className="font-bold text-white">{d.driver_id}</span>
                <span className="text-slate-300 truncate text-[11px]">{d.name}</span>
              </div>

              <div className="col-span-3 text-f1-muted truncate text-[11px]">
                {d.team}
              </div>

              <div className="col-span-2 text-right font-medium">
                {d.is_retired ? (
                  <span className="text-rose-400 text-[11px]">Abandono</span>
                ) : (
                  <span>{formatGap(d.gap_to_leader)}</span>
                )}
              </div>

              <div className="col-span-2 flex items-center justify-center gap-2 text-[11px]">
                <span className="text-f1-muted flex items-center gap-0.5">
                  <Wrench className="w-2.5 h-2.5" />
                  {d.pit_stops_made}
                </span>
                <span
                  className={
                    overallFastestLap?.driver === d.driver_id
                      ? "text-purple-400 font-bold"
                      : "text-slate-400"
                  }
                >
                  {formatLapTime(d.fastest_lap)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Ações Inferiores */}
      <div className="mt-4 pt-3 border-t border-f1-border/80 flex items-center justify-between">
        <Link
          to="/setup"
          className="flex items-center gap-2 px-4 py-2 bg-f1-red hover:bg-red-700 text-white rounded-lg font-bold text-xs transition-all shadow"
        >
          <PlusCircle className="w-4 h-4" />
          Configurar Nova Corrida
        </Link>

        {onRestart && (
          <button
            type="button"
            onClick={onRestart}
            className="flex items-center gap-2 px-4 py-2 bg-f1-card hover:bg-f1-border border border-f1-border text-slate-200 hover:text-white rounded-lg font-semibold text-xs transition-colors"
          >
            <RotateCcw className="w-4 h-4 text-amber-400" />
            Reiniciar Mesma Corrida
          </button>
        )}
      </div>
    </div>
  );
};
