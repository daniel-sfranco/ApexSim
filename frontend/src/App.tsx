import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { SetupScreen } from "@/screens/SetupScreen";
import { CockpitScreen } from "@/screens/CockpitScreen";

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SetupScreen />} />
        <Route path="/setup" element={<SetupScreen />} />
        <Route path="/race/:id" element={<CockpitScreen />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
