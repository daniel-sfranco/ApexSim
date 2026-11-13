import { useEffect, useRef, useCallback } from "react";
import { useRaceStore } from "@/store/raceStore";
import { LapUpdate, EventUpdate } from "@/types";

export function useRaceWebSocket(raceId?: string) {
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const {
    processLapUpdate,
    addEvent,
    setConnectionStatus,
    isPaused,
    setPaused,
    speedMultiplier,
    setSpeedMultiplier,
  } = useRaceStore();

  const getWsUrl = useCallback(() => {
    // Porta padrão da API FastAPI é 8000; se definida variável de ambiente, utiliza-a
    const defaultHost =
      typeof window !== "undefined" ? window.location.hostname : "localhost";
    const wsBase =
      (import.meta as any).env?.VITE_WS_URL ||
      (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_WS_URL) ||
      `ws://${defaultHost}:8000`;

    if (raceId) {
      return `${wsBase}/ws/races/${raceId}`;
    }
    return wsBase;
  }, [raceId]);

  const connect = useCallback(() => {
    if (socketRef.current && (socketRef.current.readyState === WebSocket.OPEN || socketRef.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    setConnectionStatus("connecting");
    const url = getWsUrl();
    console.log(`[useRaceWebSocket] Conectando a ${url}...`);

    try {
      const ws = new WebSocket(url);
      socketRef.current = ws;

      ws.onopen = () => {
        console.log("[useRaceWebSocket] Conexão estabelecida com sucesso!");
        setConnectionStatus("connected");

        // Envia imediatamente a configuração da corrida (grid, voltas, circuito, pneus)
        // para reiniciar a simulação a partir da volta 0 com o novo grid sorteado
        const { config } = useRaceStore.getState();
        if (config && ws.readyState === WebSocket.OPEN) {
          const initPayload = {
            action: "restart",
            race_id: raceId,
            circuit_id: config.circuitId,
            total_laps: config.totalLaps,
            seed: config.seed,
            weather: config.weather,
            grid: config.grid,
            initial_strategy: config.initialStrategy,
          };
          console.log("[useRaceWebSocket] Inicializando simulação com grid sorteado:", initPayload);
          ws.send(JSON.stringify(initPayload));
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "lap_update") {
            // Ignora envelopes de corrida antiga em andamento/finalizada
            if (raceId && data.race_id && data.race_id !== raceId && data.current_lap > 0) {
              console.log(
                `[useRaceWebSocket] Ignorando lap_update antigo (${data.race_id}, volta ${data.current_lap})`
              );
              return;
            }
            processLapUpdate(data as LapUpdate);
          } else if (data.type === "event_update") {
            if (raceId && data.race_id && data.race_id !== raceId) {
              return;
            }
            addEvent(data as EventUpdate);
          }
        } catch (err) {
          console.error("[useRaceWebSocket] Erro ao analisar mensagem:", err);
        }
      };

      ws.onerror = (err) => {
        console.warn("[useRaceWebSocket] Erro na conexão WebSocket:", err);
        setConnectionStatus("error");
      };

      ws.onclose = () => {
        console.log("[useRaceWebSocket] Conexão encerrada. Tentando reconectar em 3s...");
        setConnectionStatus("disconnected");
        socketRef.current = null;
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      };
    } catch (err) {
      console.error("[useRaceWebSocket] Falha ao instanciar WebSocket:", err);
      setConnectionStatus("error");
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    }
  }, [getWsUrl, processLapUpdate, addEvent, setConnectionStatus, raceId]);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [connect]);

  // Enviar comando genérico
  const sendCommand = useCallback((cmd: Record<string, unknown>) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(cmd));
    } else {
      console.warn("[useRaceWebSocket] Não foi possível enviar comando: socket não conectado");
    }
  }, []);

  const togglePause = useCallback(() => {
    const nextState = !isPaused;
    setPaused(nextState);
    sendCommand({ action: nextState ? "pause" : "resume" });
  }, [isPaused, setPaused, sendCommand]);

  const changeSpeed = useCallback(
    (speed: number) => {
      setSpeedMultiplier(speed);
      sendCommand({ action: "set_speed", speed_multiplier: speed });
    },
    [setSpeedMultiplier, sendCommand]
  );

  const restart = useCallback(
    (totalLaps?: number, circuitId?: string) => {
      const { config, resetRace } = useRaceStore.getState();
      resetRace();
      sendCommand({
        action: "restart",
        race_id: raceId,
        total_laps: totalLaps ?? config.totalLaps,
        circuit_id: circuitId ?? config.circuitId,
        grid: config.grid,
        initial_strategy: config.initialStrategy,
      });
    },
    [sendCommand, raceId]
  );

  return {
    togglePause,
    changeSpeed,
    restart,
    isPaused,
    speedMultiplier,
  };
}
