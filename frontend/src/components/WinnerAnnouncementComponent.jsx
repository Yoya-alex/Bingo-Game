import BingoGridComponent from "./BingoGridComponent.jsx";
import { useI18n } from "../i18n/LanguageContext.jsx";

export default function WinnerAnnouncementComponent({ winnerName, prizeAmount, winnerCard, calledNumbers, countdown }) {
  const { t } = useI18n();
  const winnerUsername = winnerCard?.winner_username;
  const displayName = winnerUsername ? `${winnerName} (@${winnerUsername})` : winnerName;
  const label = winnerName ? `${displayName} ${t("common.wins")}` : t("common.winnerDeclared");
  
  return (
    <section className="component winner-card" id="winnerAnnouncementComponent">
      <div className="component-title">{t("common.winnerAnnouncement")}</div>
      <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{label}</div>
      <p className="subtitle">{t("common.prize")}: {prizeAmount} Birr</p>
      {Number.isFinite(countdown) && countdown >= 0 && (
        <p className="subtitle">{t("common.nextRoundStartsIn", { seconds: countdown })}</p>
      )}
      {winnerCard?.grid && (
        <BingoGridComponent
          id="winnerGridComponent"
          title={`${t("common.card")} #${winnerCard.card_number}`}
          grid={winnerCard.grid}
          calledNumbers={calledNumbers || []}
          interactive={false}
        />
      )}
    </section>
  );
}
