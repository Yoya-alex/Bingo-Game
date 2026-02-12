import { Routes, Route, Navigate } from "react-router-dom";
import LobbyPage from "./pages/LobbyPage.jsx";
import PlayPage from "./pages/PlayPage.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/lobby/:telegramId" element={<LobbyPage />} />
      <Route path="/play/:telegramId/:gameId" element={<PlayPage />} />
      <Route path="*" element={<Navigate to="/lobby/0" replace />} />
    </Routes>
  );
}
