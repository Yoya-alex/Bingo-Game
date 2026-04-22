import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { useSettings } from "../context/SettingsContext.jsx";

export default function SettingsButton() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef(null);
  const location = useLocation();
  const { language, setLanguage, t } = useI18n();
  const { theme, toggleTheme, voiceEnabled, setVoiceEnabled } = useSettings();

  const isPlayPage = useMemo(() => location.pathname.startsWith("/play/"), [location.pathname]);
  const voiceSupported = useMemo(
    () => typeof window !== "undefined" && "speechSynthesis" in window && typeof window.SpeechSynthesisUtterance !== "undefined",
    []
  );

  useEffect(() => {
    function handlePointerDown(event) {
      if (!panelRef.current) {
        return;
      }
      if (!panelRef.current.contains(event.target)) {
        setOpen(false);
      }
    }

    function handleEscape(event) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  return (
    <>
      {open && <button type="button" className="settings-overlay" aria-label="Close settings" onClick={() => setOpen(false)} />}

      <div className="settings-shell" ref={panelRef}>
        <button
          className="theme-toggle settings-toggle"
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          aria-label="Settings"
          aria-expanded={open}
        >
          ⚙
        </button>

        {open && (
          <div className="settings-panel" role="dialog" aria-label="Settings panel">
            <div className="settings-row">
              <span className="settings-label">{t("app.languageToggle")}</span>
              <div className="settings-segment" role="group" aria-label={t("app.languageToggle")}>
                <button
                  type="button"
                  className={`settings-option${language === "en" ? " active" : ""}`}
                  onClick={() => setLanguage("en")}
                >
                  {t("app.englishShort")}
                </button>
                <button
                  type="button"
                  className={`settings-option${language === "am" ? " active" : ""}`}
                  onClick={() => setLanguage("am")}
                >
                  {t("app.amharicShort")}
                </button>
                <button
                  type="button"
                  className={`settings-option${language === "om" ? " active" : ""}`}
                  onClick={() => setLanguage("om")}
                >
                  {t("app.oromoShort")}
                </button>
              </div>
            </div>

            <div className="settings-row">
              <span className="settings-label">{t("app.toggleNightMode")}</span>
              <button type="button" className="settings-switch" onClick={toggleTheme}>
                {theme === "dark" ? `${t("app.light")}` : `${t("app.night")}`}
              </button>
            </div>

            <div className="settings-row">
              <span className="settings-label">{t("profile.voiceAnnouncements")}</span>
              <button
                type="button"
                className="settings-switch"
                disabled={!voiceSupported}
                onClick={() => setVoiceEnabled((prev) => !prev)}
              >
                {!voiceSupported ? t("play.voiceUnsupportedShort") : voiceEnabled ? t("play.voiceOn") : t("play.voiceOff")}
              </button>
            </div>

            {!isPlayPage && <div className="settings-hint">{t("common.game")} page only</div>}
          </div>
        )}
      </div>
    </>
  );
}
