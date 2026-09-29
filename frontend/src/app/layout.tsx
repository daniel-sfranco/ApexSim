import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ApexSim — Simulador de Fórmula 1",
  description: "Plataforma de Simulação de Corridas de F1 e Telemetria em Tempo Real.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="bg-f1-dark text-slate-100 min-h-screen antialiased selection:bg-f1-red selection:text-white">
        {children}
      </body>
    </html>
  );
}
