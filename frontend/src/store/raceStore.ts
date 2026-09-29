import { create } from "zustand";
import {
  RaceConfig,
  LapUpdate,
  EventUpdate,
  EnrichedDriverState,
} from "@/types";
import { DEFAULT_DRIVERS, CIRCUITS, F1_TEAMS } from "@/lib/constants";

interface RaceStoreState {
  // Configuração inicial da corrida
  config: RaceConfig;

  // Estado atual recebido via WebSocket
  currentLapData: LapUpdate | null;
  drivers: EnrichedDriverState[];
  previousPositions: Record<string, number>;
  events: EventUpdate[];

  // Controles de execução
  isPaused: boolean;
  speedMultiplier: number;
  connectionStatus: "disconnected" | "connecting" | "connected" | "error";
  isFinished: boolean;

  // Ações
  setRaceConfig: (partial: Partial<RaceConfig>) => void;
  reorderGrid: (newGrid: string[]) => void;
  processLapUpdate: (update: LapUpdate) => void;
  addEvent: (event: EventUpdate) => void;
  setPaused: (paused: boolean) => void;
  setSpeedMultiplier: (speed: number) => void;
  setConnectionStatus: (status: "disconnected" | "connecting" | "connected" | "error") => void;
  resetRace: () => void;
}

const initialConfig: RaceConfig = {
  circuitId: "interlagos",
  circuitName: "Autódromo de Interlagos",
  totalLaps: 53,
  seed: 42,
  weather: "DRY",
  trackTemp: 32.0,
  grid: DEFAULT_DRIVERS.map((d) => d.code),
  initialStrategy: DEFAULT_DRIVERS.reduce(
    (acc, d) => ({ ...acc, [d.code]: d.defaultTyre }),
    {}
  ),
};

// Gera drivers iniciais enriquecidos a partir do grid configurado
function buildInitialDrivers(grid: string[]): EnrichedDriverState[] {
  return grid.map((driverCode, index) => {
    const driverRef =
      DEFAULT_DRIVERS.find((d) => d.code === driverCode) ||
      DEFAULT_DRIVERS[index] || {
        code: driverCode,
        name: driverCode,
        team: "Independent",
        teamColor: "#64748b",
        defaultTyre: "MEDIUM",
      };

    return {
      driver_id: driverRef.code,
      name: driverRef.name,
      team: driverRef.team,
      teamColor: driverRef.teamColor,
      position: index + 1,
      positionChange: 0,
      gap_to_leader: index === 0 ? 0.0 : index * 1.5,
      gap_to_ahead: index === 0 ? null : 1.5,
      last_lap_time: null,
      tyre_compound: driverRef.defaultTyre,
      tyre_age: 0,
      fuel_load_kg: 105.0,
      pit_status: "NONE",
      pit_stops_made: 0,
      is_retired: false,
      drs_active: false,
      distance_m: 0,
    };
  });
}

export const useRaceStore = create<RaceStoreState>((set, get) => ({
  config: initialConfig,
  currentLapData: null,
  drivers: buildInitialDrivers(initialConfig.grid),
  previousPositions: {},
  events: [],
  isPaused: false,
  speedMultiplier: 1.0,
  connectionStatus: "disconnected",
  isFinished: false,

  setRaceConfig: (partial) => {
    set((state) => {
      const updatedConfig = { ...state.config, ...partial };
      if (partial.circuitId && !partial.circuitName) {
        const found = CIRCUITS.find((c) => c.id === partial.circuitId);
        if (found) {
          updatedConfig.circuitName = found.name;
          if (!partial.totalLaps) {
            updatedConfig.totalLaps = found.defaultLaps;
          }
        }
      }
      return {
        config: updatedConfig,
        drivers: buildInitialDrivers(updatedConfig.grid),
      };
    });
  },

  reorderGrid: (newGrid) => {
    set((state) => ({
      config: { ...state.config, grid: newGrid },
      drivers: buildInitialDrivers(newGrid),
    }));
  },

  processLapUpdate: (update) => {
    const { previousPositions, drivers: currentDrivers } = get();

    // Mapear melhor tempo de volta anterior
    const bestTimesMap: Record<string, number | undefined> = {};
    currentDrivers.forEach((d) => {
      if (d.bestLapTime) bestTimesMap[d.driver_id] = d.bestLapTime;
    });

    // Ordenar pilotos por posição
    const sortedRaw = [...update.drivers].sort((a, b) => a.position - b.position);

    const newPositions: Record<string, number> = {};
    const enriched: EnrichedDriverState[] = sortedRaw.map((d) => {
      newPositions[d.driver_id] = d.position;

      // Calcular variação de posição (+1 = subiu uma posição, -1 = caiu)
      const prevPos = previousPositions[d.driver_id] ?? d.position;
      const positionChange = prevPos - d.position;

      // Identificar cor da equipe
      const teamInfo = F1_TEAMS[d.team];
      const fallbackDriver = DEFAULT_DRIVERS.find((item) => item.code === d.driver_id);
      const teamColor = teamInfo?.color || fallbackDriver?.teamColor || "#8E9AA8";

      // Melhor volta pessoal
      const prevBest = bestTimesMap[d.driver_id];
      const bestLapTime =
        d.last_lap_time && (!prevBest || d.last_lap_time < prevBest)
          ? d.last_lap_time
          : prevBest;

      return {
        ...d,
        teamColor,
        positionChange,
        bestLapTime,
      };
    });

    const isFinished = update.current_lap >= update.total_laps;

    set({
      currentLapData: update,
      drivers: enriched,
      previousPositions: newPositions,
      isFinished,
    });
  },

  addEvent: (event) => {
    set((state) => ({
      events: [event, ...state.events].slice(0, 50), // guarda os ultimos 50 eventos
    }));
  },

  setPaused: (isPaused) => set({ isPaused }),

  setSpeedMultiplier: (speedMultiplier) => set({ speedMultiplier }),

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),

  resetRace: () => {
    const { config } = get();
    set({
      currentLapData: null,
      drivers: buildInitialDrivers(config.grid),
      previousPositions: {},
      events: [],
      isPaused: false,
      isFinished: false,
    });
  },
}));
