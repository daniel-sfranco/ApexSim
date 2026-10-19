import type { components } from "./api";

// Tipos extraídos diretamente do schema OpenAPI gerado
export type TyreCompound = components["schemas"]["TyreCompound"];
export type TrackStatus = components["schemas"]["TrackStatus"];
export type PitStatus = components["schemas"]["PitStatus"];
export type WeatherCondition = components["schemas"]["WeatherCondition"];
export type DriverUpdate = components["schemas"]["DriverUpdate"];
export type LapUpdate = components["schemas"]["LapUpdate"];
export type EventUpdate = components["schemas"]["EventUpdate"];
export type ClientCommand = components["schemas"]["ClientCommand"];
export type CreateRaceRequest = components["schemas"]["CreateRaceRequest"];
export type CreateRaceResponse = components["schemas"]["CreateRaceResponse"];
export type CircuitGeometry = components["schemas"]["CircuitGeometry"];
export type CircuitPoint = components["schemas"]["CircuitPoint"];

// Estrutura para equipes da F1 com identificação visual
export interface TeamInfo {
  name: string;
  shortName: string;
  color: string;
  secondaryColor?: string;
}

// Configuração inicial da corrida escolhida pelo usuário
export interface RaceConfig {
  circuitId: string;
  circuitName: string;
  totalLaps: number;
  seed: number;
  weather: WeatherCondition;
  trackTemp: number;
  grid: string[]; // driver codes em ordem
  initialStrategy?: Record<string, TyreCompound>;
}

// Estado enriquecido do piloto para a interface (Timing Tower)
export interface EnrichedDriverState extends DriverUpdate {
  teamColor: string;
  positionChange: number; // >0 ganhou posições, <0 perdeu posições, 0 manteve
  bestLapTime?: number;
}
