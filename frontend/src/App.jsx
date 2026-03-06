import { useEffect, useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import HomePage from "./pages/HomePage.jsx";
import LobbyPage from "./pages/LobbyPage.jsx";
import PlayPage from "./pages/PlayPage.jsx";
import ProfilePage from "./pages/ProfilePage.jsx";
import TrophyPage from "./pages/TrophyPage.jsx";
import WalletPage from "./pages/WalletPage.jsx";

const THEME_KEY = "bingo-theme";

function getInitialTheme() {
  if (typeof window === "undefined") {
    return "dark";
  }

  const savedTheme = window.localStorage.getItem(THEME_KEY);
  if (savedTheme === "light" || savedTheme === "dark") {
    return savedTheme;
  }

  return "dark";
}

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((prevTheme) => (prevTheme === "dark" ? "light" : "dark"));
  }

  return (
    <>
      <button className="theme-toggle" type="button" onClick={toggleTheme} aria-label="Toggle night mode">
        {theme === "dark" ? "☀️ Light" : "🌙 Night"}
      </button>
      <Routes>
        <Route path="/home/:telegramId" element={<HomePage />} />
        <Route path="/profile/:telegramId" element={<ProfilePage />} />
        <Route path="/trophy/:telegramId" element={<TrophyPage />} />
        <Route path="/wallet/:telegramId" element={<WalletPage />} />
        <Route path="/lobby/:telegramId" element={<LobbyPage />} />
        <Route path="/play/:telegramId/:gameId" element={<PlayPage />} />
        <Route path="*" element={<Navigate to="/home/0" replace />} />
      </Routes>
    </>
  );
}
