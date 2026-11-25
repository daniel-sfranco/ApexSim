import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useRaceStore } from "@/store/raceStore";
import { CIRCUITS, DEFAULT_DRIVERS, TYRE_INFO } from "@/lib/constants";
import { TyreCompound, WeatherCondition, CreateRaceRequest } from "@/types";
import { checkHealth, createRace } from "@/lib/api";
import {
  Trophy,
  Shuffle,
  ChevronUp,
  ChevronDown,
  Flag,
  CloudSun,
  ArrowRight,
  Server,
  CheckCircle2,
  AlertTriangle,
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
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Checa status da API backend ao montar o componente
  useEffect(() => {
    checkHealth()
      .then(() => {
        setApiStatus("online");
      })
      .catch(() => {
        setApiStatus("offline");
      });
  }, []);

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

  // Submissão do Setup com Integração à API POST /api/races
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsStarting(true);
    setStatusMessage(null);

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

    // Cria a corrida no backend e usa o `race_id` devolvido: é ele que permite ao
    // WebSocket carregar circuito, voltas e clima gravados pela API. Se a API
    // estiver indisponível, cai no modo memória com um id local.
    let targetRaceId = "race-" + Math.random().toString(36).substring(2, 9);

    const requestBody: CreateRaceRequest = {
      circuit_id: selectedCircuit,
      total_laps: Number(totalLaps),
      seed: Number(seed),
      weather,
      track_temp: Number(trackTemp),
      grid,
      // Apenas pilotos presentes no grid, como exige o contrato da API.
      initial_tyres: Object.fromEntries(
        Object.entries(startingTyres).filter(([code]) => grid.includes(code)),
      ),
    };

    try {
      const apiResponse = await createRace(requestBody);
      if (typeof apiResponse?.race_id === "string" && apiResponse.race_id) {
        targetRaceId = apiResponse.race_id;
        console.log(
          `[SetupForm] Corrida criada no backend com ID: ${targetRaceId}`,
        );
      }
    } catch (err: any) {
    } catch (err: any) {
      console.warn(
        "[SetupForm] API backend não respondeu; usando corrida em memória:",
        err?.message || err,
      );
      setStatusMessage(
        "API backend offline ou indisponível. Iniciando cockpit em modo de simulação autônoma...",
      );
      setStatusMessage("API backend offline ou indisponível. Iniciando cockpit em modo de simulação autônoma...");
    }

    setTimeout(() => {
      navigate(`/race/${targetRaceId}`);
    }, 400);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8 font-sans max-w-6xl mx-auto">
      {/* Indicador de Status da API */}
      <div className="flex items-center justify-between bg-f1-surface border border-f1-border rounded-lg px-4 py-2.5 text-xs font-mono">
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 text-f1-muted" />
          <span className="text-slate-300 font-semibold">Status do Servidor API:</span>
          {apiStatus === "checking" && (
            <span className="text-amber-400 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
              Verificando conexão...
            </span>
          )}
          {apiStatus === "online" && (
            <span className="text-emerald-400 flex items-center gap-1 font-bold">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              API ApexSim Online (FastAPI :8000)
            </span>
          )}
          {apiStatus === "offline" && (
            <span className="text-amber-400/90 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              API Offline (Usando simulação local / Mock)
            </span>
          )}
        </div>

        <span className="text-[11px] text-f1-muted">
          Contratos D2, D3 e D4 Ativos
        </span>
      </div>

      {statusMessage && (
        <div className="p-3 bg-amber-950/40 border border-amber-600/60 rounded-lg text-xs font-mono text-amber-200">
          {statusMessage}
        </div>
      )}

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
      <section className="bg-f1-surface border border-f1-border rounded-xl p-6 shadow-xl">
        <div className="flex items-center gap-2 mb-4">
          <CloudSun className="w-5 h-5 text-f1-red" />
          <h2 className="text-lg font-bold text-white uppercase tracking-wider font-mono">
            2. Condições da Pista e Simulação
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 font-mono text-sm">
          {/* Voltas Totais */}
          <div>
            <label className="block text-xs text-f1-muted uppercase mb-2">
              Voltas Totais
            </label>
            <input
              type="number"
              min={1}
              max={100}
              value={totalLaps}
              onChange={(e) => setTotalLaps(Number(e.target.value))}
              className="w-full bg-f1-card border border-f1-border rounded px-3 py-2 text-white focus:outline-none focus:border-f1-red"
            />
          </div>

          {/* Clima */}
          <div>
            <label className="block text-xs text-f1-muted uppercase mb-2">
              Clima Predominante
            </label>
            <select
              value={weather}
              onChange={(e) => setWeather(e.target.value as WeatherCondition)}
              className="w-full bg-f1-card border border-f1-border rounded px-3 py-2 text-white focus:outline-none focus:border-f1-red"
            >
              <option value="DRY">Seco (Pista Seca)</option>
              <option value="DAMP">Úmido (Damp)</option>
              <option value="WET">Chuva (Pista Molhada)</option>
            </select>
          </div>

          {/* Temperatura da Pista */}
          <div>
            <label className="block text-xs text-f1-muted uppercase mb-2">
              Temp. da Pista (°C)
            </label>
            <input
              type="number"
              min={10}
              max={60}
              value={trackTemp}
              onChange={(e) => setTrackTemp(Number(e.target.value))}
              className="w-full bg-f1-card border border-f1-border rounded px-3 py-2 text-white focus:outline-none focus:border-f1-red"
            />
          </div>

          {/* Seed Aleatório */}
          <div>
            <label className="block text-xs text-f1-muted uppercase mb-2">
              Seed Determinística
            </label>
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              className="w-full bg-f1-card border border-f1-border rounded px-3 py-2 text-white focus:outline-none focus:border-f1-red"
            />
          </div>
        </div>
      </section>

      {/* 3. GRID DE LARGADA E ESTRATÉGIA INICIAL */}
      <section className="bg-f1-surface border border-f1-border rounded-xl p-6 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Trophy className="w-5 h-5 text-f1-red" />
            <h2 className="text-lg font-bold text-white uppercase tracking-wider font-mono">
              3. Grid de Largada e Compostos Iniciais (20 Pilotos)
            </h2>
          </div>

          <button
            type="button"
            onClick={handleShuffleGrid}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-f1-card hover:bg-f1-border border border-f1-border text-xs font-mono text-slate-300 hover:text-white transition-colors"
          >
            <Shuffle className="w-3.5 h-3.5 text-amber-400" />
            Sortear Posições
          </button>
        </div>

        <p className="text-xs text-f1-muted mb-4 font-mono">
          Reordene os pilotos para a largada e escolha o composto inicial de cada um (Soft, Medium, Hard).
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono">
          {grid.map((code, idx) => {
            const driverInfo = DEFAULT_DRIVERS.find((d) => d.code === code) || {
              code,
              name: code,
              team: "Independente",
              teamColor: "#8E9AA8",
              defaultTyre: "MEDIUM" as TyreCompound,
            };
            const currentTyre = startingTyres[code] || driverInfo.defaultTyre;

            return (
              <div
                key={code}
                className="flex items-center justify-between p-2.5 rounded-lg bg-f1-dark/80 border border-f1-border/60 hover:border-slate-500 transition-colors text-xs"
              >
                {/* Posição e Nome */}
                <div className="flex items-center gap-2 overflow-hidden">
                  <span className="font-bold text-f1-muted w-5 text-center">
                    {idx + 1}º
                  </span>
                  <div
                    className="w-1.5 h-5 rounded-full flex-shrink-0"
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
