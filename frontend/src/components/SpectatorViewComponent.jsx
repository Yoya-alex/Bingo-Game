export default function SpectatorViewComponent({ id = "spectatorViewComponent", title = "Spectator View" }) {
  return (
    <section className="component spectator-info" id={id}>
      <div className="component-title">{title}</div>
      <div className="spectator-content">
        <p className="spectator-message">You are watching this round.</p>
        <p className="subtitle">This card slot is read-only for spectators. Join the next round to play.</p>
      </div>
    </section>
  );
}
