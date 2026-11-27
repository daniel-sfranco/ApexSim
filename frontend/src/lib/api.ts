import {
  CreateRaceRequest,
  CreateRaceResponse,
  RaceDetailsResponse,
  RaceResultsResponse,
  TrackMapData,
  CircuitGeometry,
} from "@/types";

export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const envUrl = (import.meta as any).env?.VITE_API_URL;
    if (envUrl) return envUrl;
    return `http://${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}

export function getWsBaseUrl(): string {
  if (typeof window !== "undefined") {
    const envWs = (import.meta as any).env?.VITE_WS_URL;
    if (envWs) return envWs;
    return `ws://${window.location.hostname}:8000`;
  }
  return "ws://localhost:8000";
}

/**
 * Healthcheck da API (GET /health)
 */
export async function checkHealth(): Promise<{ status: string }> {
  const url = `${getApiBaseUrl()}/health`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Falha no healthcheck: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Criação de uma nova corrida (POST /api/races)
 */
export async function createRace(
  request: CreateRaceRequest,
): Promise<CreateRaceResponse> {
  const url = `${getApiBaseUrl()}/api/races`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    let errorDetail = `Erro HTTP ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail =
          typeof errJson.detail === "string"
            ? errJson.detail
            : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

/**
 * Consulta de estado da corrida (GET /api/races/{race_id})
 */
export async function getRaceDetails(
  raceId: string,
): Promise<RaceDetailsResponse> {
  const url = `${getApiBaseUrl()}/api/races/${raceId}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Erro ao buscar detalhes da corrida: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Classificação calculada e analytics pós-corrida (GET /api/races/{race_id}/results)
 */
export async function getRaceResults(
  raceId: string,
): Promise<RaceResultsResponse> {
  const url = `${getApiBaseUrl()}/api/races/${raceId}/results`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Erro ao buscar resultados da corrida: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Geometria pura do circuito (GET /circuits/{circuit_id}.json)
 */
export async function getCircuitGeometry(
  circuitId: string,
): Promise<CircuitGeometry> {
  // Tenta carregar primeiro da API, depois fallback para o asset público local
  const urls = [
    `${getApiBaseUrl()}/circuits/${circuitId}.json`,
    `/circuits/${circuitId}.json`,
  ];

  for (const url of urls) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // continua tentando próxima URL
    }
  }

  throw new Error(`Geometria do circuito ${circuitId} não encontrada`);
}

/**
 * Mapa semântico de pista completo com anotações e zonas (GET /api/track-maps/{circuit_id})
 */
export async function getTrackMap(circuitId: string): Promise<TrackMapData> {
  const urls = [
    `${getApiBaseUrl()}/api/track-maps/${circuitId}`,
    `/track_maps/${circuitId}.json`,
    `${getApiBaseUrl()}/circuits/${circuitId}.json`,
    `/circuits/${circuitId}.json`,
  ];

  for (const url of urls) {
    try {
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (data.points && data.points.length > 0) {
          return data;
        }
      }
    } catch {
      // continua tentando próxima URL
    }
  }

  throw new Error(`Mapa de pista do circuito ${circuitId} não encontrado`);
}
