import { useMemo, useState } from "react";
import BingoGridComponent from "./BingoGridComponent.jsx";
import { useI18n } from "../i18n/LanguageContext.jsx";

function detectWinningPatterns(grid, calledNumbers = []) {
  if (!Array.isArray(grid) || grid.length !== 5) {
    return [];
  }

  const calledSet = new Set((calledNumbers || []).map((value) => Number(value)));
  const patterns = [];

  const isMarked = (row, col) => {
    const cell = grid[row]?.[col];
    if (cell === null) {
      return true;
    }
    return calledSet.has(Number(cell));
  };

  for (let row = 0; row < 5; row += 1) {
    if ([0, 1, 2, 3, 4].every((col) => isMarked(row, col))) {
      patterns.push(`Row ${row + 1}`);
    }
  }

  for (let col = 0; col < 5; col += 1) {
    if ([0, 1, 2, 3, 4].every((row) => isMarked(row, col))) {
      patterns.push(`Column ${col + 1}`);
    }
  }

  if ([0, 1, 2, 3, 4].every((index) => isMarked(index, index))) {
    patterns.push("Main diagonal");
  }
  if ([0, 1, 2, 3, 4].every((index) => isMarked(index, 4 - index))) {
    patterns.push("Anti diagonal");
  }

  return patterns;
}

export default function WinnerAnnouncementComponent({
  winnerName,
  prizeAmount,
  winnerCard,
  calledNumbers,
  countdown,
  gameId,
  stakeAmount,
  totalPlayers,
  currentTelegramId,
  isCurrentUserWinner,
  onPlayNextRound,
}) {
  const { t } = useI18n();
  const [shareCopied, setShareCopied] = useState(false);

  const winnerTelegramId = Number(winnerCard?.winner_telegram_id);
  const localTelegramId = Number(currentTelegramId);
  const resolvedIsWinner =
    typeof isCurrentUserWinner === "boolean"
      ? isCurrentUserWinner
      : Number.isFinite(winnerTelegramId) && Number.isFinite(localTelegramId) && winnerTelegramId === localTelegramId;

  const displayName = winnerName;
  const label = winnerName ? `${displayName} ${t("common.wins")}` : t("common.winnerDeclared");

  const normalizedPrize = Number(prizeAmount) || 0;
  const normalizedStake = Number(stakeAmount);
  const normalizedPlayers = Number(totalPlayers);
  const totalPot = Number.isFinite(normalizedStake) && Number.isFinite(normalizedPlayers) ? normalizedStake * normalizedPlayers : null;
  const platformFee = totalPot !== null ? Math.max(totalPot - normalizedPrize, 0) : null;

  const winningPatterns = useMemo(
    () => detectWinningPatterns(winnerCard?.grid, calledNumbers || []),
    [winnerCard?.grid, calledNumbers]
  );

  const prizeFormatter = useMemo(
    () =>
      new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    []
  );

  async function handleShare() {
    const summary = [
      `Winner: ${displayName || "Unknown"}`,
      `Prize: ${prizeFormatter.format(normalizedPrize)} Birr`,
      Number.isFinite(Number(gameId)) ? `Game #${gameId}` : null,
    ]
      .filter(Boolean)
      .join(" | ");

    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(summary);
        setShareCopied(true);
        setTimeout(() => setShareCopied(false), 1800);
      }
    } catch {
      setShareCopied(false);
    }
  }

  return (
    <section className={`component winner-card${resolvedIsWinner ? " is-self" : ""}`} id="winnerAnnouncementComponent">
      <div className="winner-header">
        <div className="component-title">{t("common.winnerAnnouncement")}</div>
        {resolvedIsWinner && <span className="winner-badge">You won</span>}
      </div>

      <div className="winner-label">{label}</div>

      <div className="winner-metadata">
        {Number.isFinite(Number(gameId)) && <span className="winner-chip">Game #{gameId}</span>}
        {Number.isFinite(normalizedStake) && <span className="winner-chip">Stake {normalizedStake} Birr</span>}
        {Number.isFinite(normalizedPlayers) && <span className="winner-chip">Players {normalizedPlayers}</span>}
      </div>

      <div className="winner-breakdown">
        <div className="winner-breakdown-row">
          <span>{t("common.prize")}</span>
          <strong>{prizeFormatter.format(normalizedPrize)} Birr</strong>
        </div>
        {totalPot !== null && (
          <div className="winner-breakdown-row muted">
            <span>Total pot</span>
            <span>{prizeFormatter.format(totalPot)} Birr</span>
          </div>
        )}
        {platformFee !== null && (
          <div className="winner-breakdown-row muted">
            <span>Platform fee</span>
            <span>{prizeFormatter.format(platformFee)} Birr</span>
          </div>
        )}
      </div>

      {!!winningPatterns.length && (
        <p className="subtitle winner-patterns">Winning pattern: {winningPatterns.join(", ")}</p>
      )}

      {Number.isFinite(countdown) && countdown >= 0 && (
        <p className="subtitle">{t("common.nextRoundStartsIn", { seconds: countdown })}</p>
      )}

      <div className="winner-actions">
        <button type="button" className="winner-action-btn" onClick={handleShare}>
          {shareCopied ? "Copied" : "Share"}
        </button>
        <button type="button" className="winner-action-btn primary" onClick={onPlayNextRound}>
          Play next round
        </button>
      </div>

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
