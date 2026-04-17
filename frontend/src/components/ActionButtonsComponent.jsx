import { useI18n } from "../i18n/LanguageContext.jsx";

export default function ActionButtonsComponent({ state, hasCard, onSelectCard, onBingo }) {
  const { t } = useI18n();
  let content = null;
  if (state === "waiting" && !hasCard) {
    content = (
      <button className="btn btn-primary" onClick={onSelectCard}>
        {t("common.selectCard")}
      </button>
    );
  } else if (state === "watching") {
    content = (
      <button className="btn btn-secondary" disabled>
        {t("common.watchingGame")}
      </button>
    );
  } else if (state === "playing" && hasCard) {
    content = (
      <button className="btn btn-success" onClick={onBingo}>
        {t("common.bingo")}
      </button>
    );
  } else {
    content = (
      <button className="btn btn-secondary" disabled>
        {t("common.waitingForNextRound")}
      </button>
    );
  }

  return <div className="action-bar">{content}</div>;
}
