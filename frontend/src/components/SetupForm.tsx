import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRaceStore } from "@/store/raceStore";
import { CIRCUITS, DEFAULT_DRIVERS, TYRE_INFO } from "@/lib/constants";
import { TyreCompound, WeatherCondition } from "@/types";
import {
  Trophy,
  Shuffle,
  ChevronUp,
  ChevronDown,
  Flag,
  CloudSun,
  Settings2,
  ArrowRight,
} from "lucide-react";

export const SetupForm: React.FC = () => {
  const navigate = useNavigate();
  const { config, setRaceConfig, reorderGrid, resetRace } = useRaceStore();

  const [selectedCircuit, setSelectedCircuit] = useState(config.circuitId);
  const [totalLaps, setTotalLaps] = useState(config.totalLaps);
  const [seed, setSeed] = useState(config.seed);
  const [weather, setWeather] = useState<WeatherCondition>(config.weather);
  const [trackTemp, setTrackTemp] = useState(config.trackTemp);
  const [grid, setGrid] = useState<string[]>(config.grid);
  const [startingTyres, setStartingTyres] = useState<Record<string, TyreCompound>>(
    config.initialStrategy || {}
  );
  const [isStarting, setIsStarting] = useState(false);

  // Mudar circuito
  const handleSelectCircuit = (circuitId: string) => {
    setSelectedCircuit(circuitId);
    const found = CIRCUITS.find((c) => c.id === circuitId);
    if (found) {
      setTotalLaps(found.defaultLaps);
    }
  };

  // Sortear Grid
  const handleShuffleGrid = () => {
    const shuffled = [...grid].sort(() => Math.random() - 0.5);
    setGrid(shuffled);
  };

  // Mover piloto para cima
  const moveUp = (index: number) => {
    if (index === 0) return;
    const next = [...grid];
    const temp = next[index];
    next[index] = next[index - 1];
    next[index - 1] = temp;
    setGrid(next);
  };

  // Mover piloto para baixo
  const moveDown = (index: number) => {
    if (index === grid.length - 1) return;
    const next = [...grid];
    const temp = next[index];
    next[index] = next[index + 1];
    next[index + 1] = temp;
    setGrid(next);
  };

  // Mudar pneu de um piloto
  const handleTyreChange = (driverCode: string, tyre: TyreCompound) => {
    setStartingTyres((prev) => ({
      ...prev,
      [driverCode]: tyre,
    }));
  };

  // Submissão do Setup
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsStarting(true);

    const circuitObj = CIRCUITS.find((c) => c.id === selectedCircuit);

    setRaceConfig({
      circuitId: selectedCircuit,
      circuitName: circuitObj?.name || "Grande Prêmio",
      totalLaps: Number(totalLaps),
      seed: Number(seed),
      weather,
      trackTemp: Number(trackTemp),
      grid,
      initialStrategy: startingTyres,
    });
    reorderGrid(grid);
    resetRace();

    // Tentar criar corrida no backend se disponível
    const raceId = "race-" + Math.random().toString(36).substring(2, 9);
    try {
      const apiUrl = (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";
      await fetch(`${apiUrl}/api/races`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          circuit_id: selectedCircuit,
          total_laps: totalLaps,
          seed,
          weather,
          track_temp: trackTemp,
          grid,
          // Apenas pilotos presentes no grid, como exige o contrato da API.
          initial_tyres: Object.fromEntries(
            Object.entries(startingTyres).filter(([code]) => grid.includes(code))
          ),
        }),
      }).catch(() => null);
    } catch {
      // Fallback gracioso
    }

    navigate(`/race/${raceId}`);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8 font-sans max-w-6xl mx-auto">
      {/* 1. SELETOR DE CIRCUITO */}
      <section className="bg-f1-surface border border-f1-border rounded-xl p-6 shadow-xl">
        <div className="flex items-center gap-2 mb-4">
          <Flag className="w-5 h-5 text-f1-red" />
          <h2 className="text-lg font-bold text-white uppercase tracking-wider font-mono">
            1. Selecione o Circuito (Contrato D3)
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {CIRCUITS.map((circuit) => {
            const isSelected = selectedCircuit === circuit.id;
            return (
              <div
                key={circuit.id}
                onClick={() => handleSelectCircuit(circuit.id)}
                className={`cursor-pointer rounded-lg p-4 border transition-all ${
                  isSelected
                    ? "bg-f1-card border-f1-red ring-1 ring-f1-red shadow-lg shadow-f1-red/10"
                    : "bg-f1-dark/60 border-f1-border hover:border-slate-500 hover:bg-f1-card/40"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-2xl">{circuit.flag}</span>
                  <span className="text-xs font-mono bg-f1-dark px-2 py-0.5 rounded text-f1-muted border border-f1-border">
                    {circuit.lengthM}m • {circuit.defaultLaps} voltas
                  </span>
                </div>
                <h3 className="font-bold text-white text-base mb-1 font-mono">
                  {circuit.name}
                </h3>
                <p className="text-xs text-f1-muted leading-relaxed">
                  {circuit.description}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* 2. CONDIÇÕES AMBIENTAIS E SIMULAÇÃO */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Clima e Temperatura */}
        <div className="bg-f1-surface border border-f1-border rounded-xl p-6 shadow-xl">
          <div className="flex items-center gap-2 mb-4">
            <CloudSun className="w-5 h-5 text-amber-400" />
            <h2 className="text-lg font-bold text-white uppercase tracking-wider font-mono">
              2. Condições Climáticas
            </h2>
          </div>

          <div className="space-y-4 font-mono text-sm">
            <div>
              <label className="block text-xs text-f1-muted mb-2 uppercase">
                Condição do Asfalto
              </label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "DRY", label: "☀️ Seco" },
                  { id: "DAMP", label: "⛅ Úmido" },
                  { id: "WET", label: "🌧️ Chuva" },
                ].map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    onClick={() => setWeather(item.id as WeatherCondition)}
                    className={`py-2 px-3 rounded border text-xs font-bold transition-colors ${
                      weather === item.id
                        ? "bg-f1-red text-white border-f1-red"
                        : "bg-f1-dark text-slate-300 border-f1-border hover:bg-f1-card"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-f1-muted uppercase">Temperatura de Pista</span>
                <span className="text-white font-bold">{trackTemp}°C</span>
              </div>
              <input
                type="range"
                min="15"
                max="55"
                value={trackTemp}
                onChange={(e) => setTrackTemp(Number(e.target.value))}
                className="w-full accent-f1-red cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-f1-muted">
                <span>15°C (Fria)</span>
                <span>35°C (Ideal)</span>
                <span>55°C (Extrema)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Parâmetros do Motor */}
        <div className="bg-f1-surface border border-f1-border rounded-xl p-6 shadow-xl">
          <div className="flex items-center gap-2 mb-4">
            <Settings2 className="w-5 h-5 text-sky-400" />
            <h2 className="text-lg font-bold text-white uppercase tracking-wider font-mono">
              3. Parâmetros da Prova
            </h2>
          </div>

          <div className="grid grid-cols-2 gap-4 font-mono text-sm">
            <div>
              <label className="block text-xs text-f1-muted mb-1 uppercase">
                Total de Voltas
              </label>
              <input
                type="number"
                min="5"
                max="100"
                value={totalLaps}
                onChange={(e) => setTotalLaps(Number(e.target.value))}
                className="w-full bg-f1-dark border border-f1-border rounded px-3 py-2 text-white font-bold focus:border-f1-red focus:outline-none"
              />
              <span className="text-[10px] text-f1-muted">Mínimo 5, Máximo 100</span>
            </div>

            <div>
              <label className="block text-xs text-f1-muted mb-1 uppercase">
                Seed Determinística
              </label>
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
                className="w-full bg-f1-dark border border-f1-border rounded px-3 py-2 text-white font-bold focus:border-f1-red focus:outline-none"
              />
              <span className="text-[10px] text-f1-muted">Mesma seed = mesma corrida</span>
            </div>
          </div>
        </div>
      </section>

      {/* 4. GRID DE LARGADA E ESTRATÉGIA INICIAL */}
      <section className="bg-f1-surface border border-f1-border rounded-xl p-6 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Trophy className="w-5 h-5 text-amber-400" />
            <h2 className="text-lg font-bold text-white uppercase tracking-wider font-mono">
              4. Grid de Largada & Compostos (20 Pilotos)
            </h2>
          </div>

          <button
            type="button"
            onClick={handleShuffleGrid}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-f1-card hover:bg-f1-border border border-f1-border text-xs font-mono font-semibold text-slate-200 transition-colors"
          >
            <Shuffle className="w-3.5 h-3.5" />
            Sortear Grid
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-xs">
          {grid.map((code, idx) => {
            const driverInfo =
              DEFAULT_DRIVERS.find((d) => d.code === code) || DEFAULT_DRIVERS[idx];
            const currentTyre = startingTyres[code] || driverInfo.defaultTyre;

            return (
              <div
                key={code}
                className="flex items-center justify-between p-2 rounded bg-f1-dark/80 border border-f1-border hover:border-slate-500 transition-colors"
              >
                {/* Posição e Identificação */}
                <div className="flex items-center gap-2">
                  <span className="w-6 text-center font-bold text-f1-muted">
                    P{idx + 1}
                  </span>
                  <div
                    className="w-1 h-5 rounded-full"
                    style={{ backgroundColor: driverInfo.teamColor }}
                  />
                  <div>
                    <span className="font-bold text-white mr-1.5">{code}</span>
                    <span className="text-f1-muted text-[11px]">
                      {driverInfo.name}
                    </span>
                  </div>
                </div>

                {/* Seletor de Pneu e Ajuste de Posição */}
                <div className="flex items-center gap-2">
                  {/* Pneu */}
                  <div className="flex items-center gap-1">
                    {(["SOFT", "MEDIUM", "HARD"] as TyreCompound[]).map((t) => {
                      const tInfo = TYRE_INFO[t];
                      const active = currentTyre === t;
                      return (
                        <button
                          key={t}
                          type="button"
                          onClick={() => handleTyreChange(code, t)}
                          className={`w-5 h-5 rounded-full text-[10px] font-bold border flex items-center justify-center transition-all ${
                            active
                              ? `${tInfo.border} bg-white text-black font-extrabold shadow`
                              : "border-f1-border text-f1-muted hover:border-slate-400"
                          }`}
                          style={active ? { borderColor: tInfo.color } : {}}
                          title={`Composto de largada: ${tInfo.label}`}
                        >
                          {tInfo.letter}
                        </button>
                      );
                    })}
                  </div>

                  {/* Botões Mover Posição */}
                  <div className="flex items-center gap-0.5">
                    <button
                      type="button"
                      disabled={idx === 0}
                      onClick={() => moveUp(idx)}
                      className="p-1 rounded hover:bg-f1-card text-f1-muted hover:text-white disabled:opacity-20"
                    >
                      <ChevronUp className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      disabled={idx === grid.length - 1}
                      onClick={() => moveDown(idx)}
                      className="p-1 rounded hover:bg-f1-card text-f1-muted hover:text-white disabled:opacity-20"
                    >
                      <ChevronDown className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* BOTÃO DE CONFIRMAÇÃO */}
      <div className="flex justify-end pt-4">
        <button
          type="submit"
          disabled={isStarting}
          className="flex items-center gap-2 px-8 py-3.5 rounded-lg bg-f1-red hover:bg-red-700 text-white font-mono font-bold tracking-wider uppercase text-sm shadow-xl shadow-f1-red/25 hover:shadow-f1-red/40 transition-all cursor-pointer disabled:opacity-50"
        >
          {isStarting ? "Inicializando Simulação..." : "Iniciar Simulação no Cockpit"}
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </form>
  );
};
