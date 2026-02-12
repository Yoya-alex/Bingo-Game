export default function ActionButtonsComponent({ state, hasCard, onSelectCard, onBingo }) {
  let content = null;
  if (state === "waiting" && !hasCard) {
    content = (
      <button className="btn btn-primary" onClick={onSelectCard}>
        Select Card
      </button>
    );
  } else if (state === "playing" && hasCard) {
    content = (
      <button className="btn btn-success" onClick={onBingo}>
        BINGO!
      </button>
    );
  } else {
    content = (
      <button className="btn btn-secondary" disabled>
        Waiting for next round
      </button>
    );
  }

  return <div className="action-bar">{content}</div>;
}
