import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { SetupScreen } from "@/screens/SetupScreen";
import { CockpitScreen } from "@/screens/CockpitScreen";
import { ErrorBoundary } from "@/components/ErrorBoundary";

export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<SetupScreen />} />
          <Route path="/setup" element={<SetupScreen />} />
          <Route path="/race/:id" element={<CockpitScreen />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
};

export default App;
