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
    // Porta padrão do Mock Server é 8080; se definida variável de ambiente, utiliza-a
    const defaultHost =
      typeof window !== "undefined" ? window.location.hostname : "localhost";
    const wsBase =
      (import.meta as any).env?.VITE_WS_URL ||
      (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_WS_URL) ||
      `ws://${defaultHost}:8080`;

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
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "lap_update") {
            processLapUpdate(data as LapUpdate);
          } else if (data.type === "event_update") {
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
  }, [getWsUrl, processLapUpdate, addEvent, setConnectionStatus]);

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
      sendCommand({ action: "restart", total_laps: totalLaps, circuit_id: circuitId });
    },
    [sendCommand]
  );

  return {
    togglePause,
    changeSpeed,
    restart,
    isPaused,
    speedMultiplier,
  };
}
