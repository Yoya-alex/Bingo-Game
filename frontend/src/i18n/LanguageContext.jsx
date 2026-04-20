import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { translations } from "./translations.js";

const STORAGE_KEY = "bingo-language";
const SUPPORTED_LANGUAGES = ["en", "am", "om"];

function normalizeLanguage(value) {
  const raw = String(value || "").trim().toLowerCase();
  return SUPPORTED_LANGUAGES.includes(raw) ? raw : "";
}

function getInitialLanguage() {
  if (typeof window === "undefined") {
    return "en";
  }

  const params = new URLSearchParams(window.location.search || "");
  const fromUrl = normalizeLanguage(params.get("lang") || params.get("language"));
  if (fromUrl) {
    return fromUrl;
  }

  const saved = (window.localStorage.getItem(STORAGE_KEY) || "").trim();
  return normalizeLanguage(saved) || "en";
}

function resolvePath(obj, path) {
  return path.split(".").reduce((acc, token) => (acc && acc[token] != null ? acc[token] : undefined), obj);
}

function interpolate(template, vars) {
  if (!vars) {
    return template;
  }
  return String(template).replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, key) => {
    const value = vars[key];
    return value == null ? "" : String(value);
  });
}

const LanguageContext = createContext({
  language: "en",
  setLanguage: () => {},
  toggleLanguage: () => {},
  t: (key, vars) => interpolate(key, vars),
});

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(getInitialLanguage);

  function setLanguage(next) {
    const normalized = SUPPORTED_LANGUAGES.includes(next) ? next : "en";
    setLanguageState(normalized);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, normalized);
    }
  }

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = language;
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, language);
    }
  }, [language]);

  function toggleLanguage() {
    const currentIndex = SUPPORTED_LANGUAGES.indexOf(language);
    const nextLanguage = SUPPORTED_LANGUAGES[(currentIndex + 1) % SUPPORTED_LANGUAGES.length];
    setLanguage(nextLanguage);
  }

  const value = useMemo(() => {
    function t(key, vars) {
      const langPack = translations[language] || translations.en;
      const fallbackPack = translations.en;
      const valueFromLang = resolvePath(langPack, key);
      const valueFromFallback = resolvePath(fallbackPack, key);
      const raw = valueFromLang ?? valueFromFallback ?? key;
      return interpolate(raw, vars);
    }

    return {
      language,
      setLanguage,
      toggleLanguage,
      t,
    };
  }, [language]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n() {
  return useContext(LanguageContext);
}
