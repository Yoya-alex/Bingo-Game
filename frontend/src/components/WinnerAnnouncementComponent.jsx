import BingoGridComponent from "./BingoGridComponent.jsx";

export default function WinnerAnnouncementComponent({ winnerName, prizeAmount, winnerCard, calledNumbers, countdown }) {
  const label = winnerName ? `${winnerName} wins!` : "Winner declared";
  return (
    <section className="component winner-card" id="winnerAnnouncementComponent">
      <div className="component-title">Winner Announcement</div>
      <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{label}</div>
      <p className="subtitle">Prize: {prizeAmount} Birr</p>
      {Number.isFinite(countdown) && countdown >= 0 && (
        <p className="subtitle">Next round starts in {countdown}s</p>
      )}
      {winnerCard?.grid && (
        <BingoGridComponent
          id="winnerGridComponent"
          title={`Winning Card #${winnerCard.card_number}`}
          grid={winnerCard.grid}
          calledNumbers={calledNumbers || []}
          interactive={false}
        />
      )}
    </section>
  );
}
