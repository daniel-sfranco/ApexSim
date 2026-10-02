import { TeamInfo, TyreCompound, TrackStatus } from "@/types";

export const F1_TEAMS: Record<string, TeamInfo> = {
  "Red Bull Racing": {
    name: "Red Bull Racing",
    shortName: "Red Bull",
    color: "#3671C6",
  },
  McLaren: {
    name: "McLaren F1 Team",
    shortName: "McLaren",
    color: "#FF8000",
  },
  Ferrari: {
    name: "Scuderia Ferrari",
    shortName: "Ferrari",
    color: "#E8002D",
  },
  Mercedes: {
    name: "Mercedes-AMG Petronas",
    shortName: "Mercedes",
    color: "#27F4D2",
  },
  "Aston Martin": {
    name: "Aston Martin Aramco",
    shortName: "Aston Martin",
    color: "#229971",
  },
  RB: {
    name: "Visa Cash App RB",
    shortName: "RB",
    color: "#6692FF",
  },
  Williams: {
    name: "Williams Racing",
    shortName: "Williams",
    color: "#64C4FF",
  },
  Alpine: {
    name: "BWT Alpine F1 Team",
    shortName: "Alpine",
    color: "#0093CC",
  },
  Haas: {
    name: "MoneyGram Haas F1 Team",
    shortName: "Haas",
    color: "#B6BABD",
  },
  "Kick Sauber": {
    name: "Stake F1 Team Kick Sauber",
    shortName: "Sauber",
    color: "#52E252",
  },
};

export interface DefaultDriver {
  code: string;
  name: string;
  number: number;
  team: string;
  teamColor: string;
  defaultTyre: TyreCompound;
}

export const DEFAULT_DRIVERS: DefaultDriver[] = [
  { code: "VER", name: "Max Verstappen", number: 1, team: "Red Bull Racing", teamColor: "#3671C6", defaultTyre: "MEDIUM" },
  { code: "NOR", name: "Lando Norris", number: 4, team: "McLaren", teamColor: "#FF8000", defaultTyre: "MEDIUM" },
  { code: "LEC", name: "Charles Leclerc", number: 16, team: "Ferrari", teamColor: "#E8002D", defaultTyre: "SOFT" },
  { code: "PIA", name: "Oscar Piastri", number: 81, team: "McLaren", teamColor: "#FF8000", defaultTyre: "MEDIUM" },
  { code: "SAI", name: "Carlos Sainz", number: 55, team: "Ferrari", teamColor: "#E8002D", defaultTyre: "SOFT" },
  { code: "HAM", name: "Lewis Hamilton", number: 44, team: "Mercedes", teamColor: "#27F4D2", defaultTyre: "HARD" },
  { code: "RUS", name: "George Russell", number: 63, team: "Mercedes", teamColor: "#27F4D2", defaultTyre: "MEDIUM" },
  { code: "PER", name: "Sergio Pérez", number: 11, team: "Red Bull Racing", teamColor: "#3671C6", defaultTyre: "HARD" },
  { code: "ALO", name: "Fernando Alonso", number: 14, team: "Aston Martin", teamColor: "#229971", defaultTyre: "MEDIUM" },
  { code: "STR", name: "Lance Stroll", number: 18, team: "Aston Martin", teamColor: "#229971", defaultTyre: "HARD" },
  { code: "TSU", name: "Yuki Tsunoda", number: 22, team: "RB", teamColor: "#6692FF", defaultTyre: "SOFT" },
  { code: "LAW", name: "Liam Lawson", number: 30, team: "RB", teamColor: "#6692FF", defaultTyre: "MEDIUM" },
  { code: "GAS", name: "Pierre Gasly", number: 10, team: "Alpine", teamColor: "#0093CC", defaultTyre: "HARD" },
  { code: "OCO", name: "Esteban Ocon", number: 31, team: "Alpine", teamColor: "#0093CC", defaultTyre: "MEDIUM" },
  { code: "ALB", name: "Alexander Albon", number: 23, team: "Williams", teamColor: "#64C4FF", defaultTyre: "MEDIUM" },
  { code: "COL", name: "Franco Colapinto", number: 43, team: "Williams", teamColor: "#64C4FF", defaultTyre: "SOFT" },
  { code: "HUL", name: "Nico Hülkenberg", number: 27, team: "Haas", teamColor: "#B6BABD", defaultTyre: "HARD" },
  { code: "MAG", name: "Kevin Magnussen", number: 20, team: "Haas", teamColor: "#B6BABD", defaultTyre: "MEDIUM" },
  { code: "BOT", name: "Valtteri Bottas", number: 77, team: "Kick Sauber", teamColor: "#52E252", defaultTyre: "HARD" },
  { code: "ZHO", name: "Zhou Guanyu", number: 24, team: "Kick Sauber", teamColor: "#52E252", defaultTyre: "MEDIUM" },
];

export interface CircuitOption {
  id: string;
  name: string;
  country: string;
  flag: string;
  lengthM: number;
  defaultLaps: number;
  description: string;
}

export const CIRCUITS: CircuitOption[] = [
  {
    id: "interlagos",
    name: "Autódromo de Interlagos",
    country: "Brasil",
    flag: "🇧🇷",
    lengthM: 4309,
    defaultLaps: 71,
    description: "Traçado anti-horário com relevo acentuado, freadas fortes e clima imprevisível.",
  },
  {
    id: "monza",
    name: "Autodromo Nazionale Monza",
    country: "Itália",
    flag: "🇮🇹",
    lengthM: 5793,
    defaultLaps: 53,
    description: "O Templo da Velocidade: longas retas de altíssima velocidade e fortes chicanes.",
  },
  {
    id: "monaco",
    name: "Circuit de Monaco",
    country: "Mônaco",
    flag: "🇲🇨",
    lengthM: 3337,
    defaultLaps: 78,
    description: "Circuito de rua clássico mais estreito e implacável do calendário da F1.",
  },
];

export const TYRE_INFO: Record<TyreCompound, { label: string; letter: string; color: string; border: string; bg: string }> = {
  SOFT: { label: "Soft", letter: "S", color: "#FF1801", border: "border-[#FF1801]", bg: "bg-[#FF1801]/10" },
  MEDIUM: { label: "Medium", letter: "M", color: "#FFD800", border: "border-[#FFD800]", bg: "bg-[#FFD800]/10" },
  HARD: { label: "Hard", letter: "H", color: "#FFFFFF", border: "border-white", bg: "bg-white/10" },
  INTERMEDIATE: { label: "Intermediate", letter: "I", color: "#39B54A", border: "border-[#39B54A]", bg: "bg-[#39B54A]/10" },
  WET: { label: "Wet", letter: "W", color: "#00A0DE", border: "border-[#00A0DE]", bg: "bg-[#00A0DE]/10" },
  UNKNOWN: { label: "Unknown", letter: "?", color: "#8E9AA8", border: "border-gray-500", bg: "bg-gray-500/10" },
};

export const TRACK_STATUS_CONFIG: Record<TrackStatus, { label: string; bg: string; text: string; border: string; pulse?: boolean }> = {
  GREEN: { label: "PISTA LIMPA", bg: "bg-emerald-500/15", text: "text-emerald-400", border: "border-emerald-500/40" },
  YELLOW: { label: "BANDEIRA AMARELA", bg: "bg-amber-500/20", text: "text-amber-400", border: "border-amber-500/50" },
  SAFETY_CAR: { label: "SAFETY CAR", bg: "bg-amber-600/30", text: "text-amber-300", border: "border-amber-500", pulse: true },
  RED: { label: "BANDEIRA VERMELHA", bg: "bg-rose-600/30", text: "text-rose-400", border: "border-rose-500", pulse: true },
};

export function formatLapTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || isNaN(seconds)) return "-";
  const mins = Math.floor(seconds / 60);
  const remSecs = (seconds % 60).toFixed(3);
  if (mins === 0) return `${remSecs}s`;
  const formattedSecs = (seconds % 60) < 10 ? `0${remSecs}` : remSecs;
  return `${mins}:${formattedSecs}`;
}

export function formatGap(gap: number | null | undefined): string {
  if (gap === null || gap === undefined) return "-";
  if (gap === 0) return "LÍDER";
  return `+${gap.toFixed(3)}s`;
}
