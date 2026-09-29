import React from "react";
import { Link } from "react-router-dom";
import { SetupForm } from "@/components/SetupForm";
import { Activity } from "lucide-react";

export const SetupScreen: React.FC = () => {
  return (
    <div className="min-h-screen bg-f1-dark text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-f1-border bg-f1-surface px-6 py-4 shadow-md">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="w-3 h-8 bg-f1-red rounded-sm"></span>
            <div>
              <h1 className="text-xl font-bold font-mono tracking-wider uppercase text-white flex items-center gap-2">
                ApexSim <span className="text-xs px-2 py-0.5 rounded bg-f1-card text-f1-muted font-normal">F1 Simulator</span>
              </h1>
              <p className="text-xs text-f1-muted font-mono">
                Configuração de Prova • Marcos M0 & M1
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono">
            <Link
              to="/race/live"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-f1-card hover:bg-f1-border border border-f1-border text-slate-300 hover:text-white transition-colors"
            >
              <Activity className="w-3.5 h-3.5 text-emerald-400" />
              Cockpit Direto
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        <div className="mb-6">
          <h2 className="text-2xl font-bold font-mono text-white mb-1">
            Configuração da Corrida
          </h2>
          <p className="text-sm text-f1-muted">
            Defina o circuito, condições meteorológicas, grid de largada e compostos iniciais.
          </p>
        </div>

        <SetupForm />
      </main>

      {/* Footer */}
      <footer className="border-t border-f1-border py-4 px-6 text-center text-xs text-f1-muted font-mono">
        ApexSim • MC857 Unicamp • Frontend & UX Anderson M. T. L. Leite
      </footer>
    </div>
  );
};
