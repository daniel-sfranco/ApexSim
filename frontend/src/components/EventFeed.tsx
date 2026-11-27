import React from "react";
import { useRaceStore } from "@/store/raceStore";
import {
  AlertTriangle,
  Flag,
  ArrowRightLeft,
  Wrench,
  ShieldAlert,
  CloudRain,
  Flame,
  XCircle,
} from "lucide-react";

export const EventFeed: React.FC = () => {
  const { events } = useRaceStore();

  const getEventIcon = (type: string) => {
    switch (type) {
      case "OVERTAKE":
        return <ArrowRightLeft className="w-3.5 h-3.5 text-sky-400" />;
      case "PIT_STOP":
        return <Wrench className="w-3.5 h-3.5 text-amber-400" />;
      case "SAFETY_CAR_DEPLOYED":
      case "SAFETY_CAR_IN":
      case "VSC_DEPLOYED":
        return <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />;
      case "WEATHER_CHANGED":
        return <CloudRain className="w-3.5 h-3.5 text-cyan-400" />;
      case "ACCIDENT":
        return <Flame className="w-3.5 h-3.5 text-rose-400" />;
      case "RETIREMENT":
        return <XCircle className="w-3.5 h-3.5 text-rose-400" />;
      case "GREEN_FLAG":
        return <Flag className="w-3.5 h-3.5 text-emerald-400" />;
      case "YELLOW_FLAG":
        return <AlertTriangle className="w-3.5 h-3.5 text-yellow-400" />;
      default:
        return <Flag className="w-3.5 h-3.5 text-f1-muted" />;
    }
  };

  return (
    <div className="bg-f1-surface border border-f1-border rounded-lg shadow-xl overflow-hidden flex flex-col h-full">
      <div className="bg-f1-dark/90 px-4 py-2.5 border-b border-f1-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-400"></span>
          <span className="text-xs font-mono font-bold tracking-wider uppercase text-white">
            Direção de Prova
          </span>
        </div>
        <span className="text-[11px] font-mono text-f1-muted">
          {events.length} Mensagens
        </span>
      </div>

      <div className="p-3 overflow-y-auto space-y-2 flex-1 font-mono text-xs">
        {events.length === 0 ? (
          <div className="text-center py-8 text-f1-muted text-xs">
            Nenhum incidente registrado. Corrida em andamento normal.
          </div>
        ) : (
          events.map((evt, idx) => (
            <div
              key={idx}
              className="p-2.5 rounded bg-f1-card border border-f1-border/60 flex items-start gap-2.5 animate-fadeIn"
            >
              <div className="p-1 rounded bg-f1-dark border border-f1-border flex-shrink-0 mt-0.5">
                {getEventIcon(evt.event_type)}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between text-[10px] text-f1-muted mb-0.5">
                  <span className="font-bold text-white uppercase">
                    {evt.event_type.replace(/_/g, " ")}
                  </span>
                  <span>Volta {evt.lap}</span>
                </div>
                <p className="text-slate-200 leading-relaxed text-xs">
                  {evt.description}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
