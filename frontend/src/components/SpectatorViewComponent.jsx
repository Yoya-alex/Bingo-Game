import { useI18n } from "../i18n/LanguageContext.jsx";

export default function SpectatorViewComponent({ id = "spectatorViewComponent", title = "Spectator View" }) {
  const { t } = useI18n();
  return (
    <section className="component spectator-info" id={id}>
      <div className="component-title">{title === "Spectator View" ? t("common.spectatorView") : title}</div>
      <div className="spectator-content">
        <p className="spectator-message">{t("common.spectatorWatching")}</p>
        <p className="subtitle">{t("common.spectatorReadonly")}</p>
      </div>
    </section>
  );
}
