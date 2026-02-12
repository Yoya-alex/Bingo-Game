export default function WinnerAnnouncementComponent({ winnerName, prizeAmount }) {
  const label = winnerName ? `${winnerName} wins!` : "Winner declared";
  return (
    <section className="component winner-card" id="winnerAnnouncementComponent">
      <div className="component-title">Winner Announcement</div>
      <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{label}</div>
      <p className="subtitle">Prize: {prizeAmount} Birr</p>
    </section>
  );
}
