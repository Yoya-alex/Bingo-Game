import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import HomePage from "./pages/HomePage.jsx";
import LobbyPage from "./pages/LobbyPage.jsx";
import PlayPage from "./pages/PlayPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import TrophyPage from "./pages/TrophyPage.jsx";
import WalletPage from "./pages/WalletPage.jsx";
import EngagementPage from "./pages/EngagementPage.jsx";
import { bootstrapAuthToken } from "./utils/auth.js";
import SettingsButton from "./components/SettingsButton.jsx";

function buildHomeTargetFromQuery() {
  if (typeof window === "undefined") {
    return "/home/0";
  }

  const params = new URLSearchParams(window.location.search || "");
  const telegramId = (params.get("telegram_id") || params.get("telegramId") || "0").trim() || "0";
  const token = (params.get("token") || "").trim();

  if (!token) {
    return `/home/${telegramId}`;
  }

  return `/home/${telegramId}?token=${encodeURIComponent(token)}`;
}

export default function App() {
  useEffect(() => {
    bootstrapAuthToken();
  }, []);

  return (
    <>
      <SettingsButton />
      <Routes>
        <Route path="/" element={<Navigate to={buildHomeTargetFromQuery()} replace />} />
        <Route path="/home/:telegramId" element={<HomePage />} />
        <Route path="/home/:telegramId/" element={<HomePage />} />
        <Route path="/profile/:telegramId" element={<ProfilePage />} />
        <Route path="/profile/:telegramId/" element={<ProfilePage />} />
        <Route path="/trophy/:telegramId" element={<TrophyPage />} />
        <Route path="/trophy/:telegramId/" element={<TrophyPage />} />
        <Route path="/wallet/:telegramId" element={<WalletPage />} />
        <Route path="/wallet/:telegramId/" element={<WalletPage />} />
        <Route path="/engagement/:telegramId" element={<EngagementPage />} />
        <Route path="/engagement/:telegramId/" element={<EngagementPage />} />
        <Route path="/lobby/:telegramId" element={<LobbyPage />} />
        <Route path="/lobby/:telegramId/" element={<LobbyPage />} />
        <Route path="/play/:telegramId/:gameId" element={<PlayPage />} />
        <Route path="/play/:telegramId/:gameId/" element={<PlayPage />} />
        <Route path="*" element={<Navigate to="/home/0" replace />} />
      </Routes>
    </>
  );
}
