import { createContext, useContext, useEffect, useMemo, useState } from "react";

const THEME_KEY = "bingo-theme";
const VOICE_KEY = "bingo-voice-enabled";

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

function getInitialVoiceEnabled() {
  if (typeof window === "undefined") {
    return false;
  }

  return window.localStorage.getItem(VOICE_KEY) === "true";
}

const SettingsContext = createContext({
  theme: "dark",
  setTheme: () => {},
  toggleTheme: () => {},
  voiceEnabled: false,
  setVoiceEnabled: () => {},
  toggleVoiceEnabled: () => {},
});

export function SettingsProvider({ children }) {
  const [theme, setTheme] = useState(getInitialTheme);
  const [voiceEnabled, setVoiceEnabled] = useState(getInitialVoiceEnabled);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", theme);
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(THEME_KEY, theme);
    }
  }, [theme]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(VOICE_KEY, String(voiceEnabled));
    }
  }, [voiceEnabled]);

  function toggleTheme() {
    setTheme((prevTheme) => (prevTheme === "dark" ? "light" : "dark"));
  }

  function toggleVoiceEnabled() {
    setVoiceEnabled((prev) => !prev);
  }

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      toggleTheme,
      voiceEnabled,
      setVoiceEnabled,
      toggleVoiceEnabled,
    }),
    [theme, voiceEnabled]
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings() {
  return useContext(SettingsContext);
}
