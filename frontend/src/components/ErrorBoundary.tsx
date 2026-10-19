import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertOctagon, RotateCcw } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[ErrorBoundary] Erro capturado:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-f1-dark text-slate-100 flex items-center justify-center p-6">
          <div className="max-w-md w-full bg-f1-surface border border-rose-800 rounded-xl p-6 shadow-2xl text-center space-y-4 font-mono">
            <div className="w-12 h-12 mx-auto rounded-full bg-rose-950/60 border border-rose-600 flex items-center justify-center text-rose-400">
              <AlertOctagon className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white uppercase tracking-wider">
                Erro de Renderização
              </h2>
              <p className="text-xs text-rose-300 mt-2 font-mono break-words bg-f1-card p-3 rounded border border-f1-border text-left">
                {this.state.error?.message || "Ocorreu um erro inesperado."}
              </p>
            </div>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.href = "/";
              }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded bg-f1-red hover:bg-red-700 text-white font-bold text-xs transition-colors shadow"
            >
              <RotateCcw className="w-4 h-4" />
              Voltar ao Início
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
