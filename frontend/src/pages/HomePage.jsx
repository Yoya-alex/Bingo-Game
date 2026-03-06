import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson } from "../api/client.js";
import NotificationComponent from "../components/NotificationComponent.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };
const POLL_MS = 2000;
const MEDB_THEME = {
  10: "medb-10",
  20: "medb-20",
  50: "medb-50",
  100: "medb-100",
};

export default function HomePage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
  const pollRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [showInfoModal, setShowInfoModal] = useState(false);
  const [data, setData] = useState({
    user: null,
    games: [],
    stakes: [10, 20, 50, 100],
    wallet_balance: 0,
  });

  const gameRows = useMemo(() => {
    if (Array.isArray(data.games) && data.games.length) {
      return data.games;
    }

    return (data.stakes || [10, 20, 50, 100]).map((stake) => ({
      game_id: null,
      stake_amount: stake,
      medb: stake,
      derash: 0,
      players: 0,
      status_label: "Waiting for players",
      state: "waiting",
      action: "join",
      action_label: "Join Now",
      user_has_card: false,
    }));
  }, [data.games, data.stakes]);

  useEffect(() => {
    setLoading(true);
    fetchJson(`/game/api/lobby-state/${telegramId}/`)
      .then((payload) => {
        setData(payload);
      })
      .catch((error) => notify("error", error.message))
      .finally(() => setLoading(false));
  }, [telegramId]);

  useEffect(() => {
    pollRef.current = setInterval(() => {
      fetchJson(`/game/api/lobby-state/${telegramId}/`)
        .then((payload) => setData(payload))
        .catch(() => notify("error", "Unable to sync lobby state."));
    }, POLL_MS);

    return () => clearInterval(pollRef.current);
  }, [telegramId]);

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  function formatBirr(value) {
    const amount = Number(value || 0);
    return `${amount.toFixed(2)} Br`;
  }

  function handleRowAction(row) {
    const stake = row.stake_amount;
    if (!stake) {
      notify("error", "Invalid game tier.");
      return;
    }

    if (row.action === "play" && row.game_id && row.state === "playing") {
      navigate(`/play/${telegramId}/${row.game_id}`);
      return;
    }

    navigate(`/lobby/${telegramId}?stake=${stake}`);
  }

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="subtitle">Loading lobby...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell lobby-shell">
      <div className="app-card lobby-card">
        <header className="lobby-header">
          <h1 className="title lobby-title">Bingo Game Lobby</h1>
          <p className="subtitle lobby-subtitle">
            {data.user?.first_name || "Player"} - Wallet {formatBirr(data.wallet_balance)}
          </p>
        </header>

        <NotificationComponent notification={notification} />

        <section className="lobby-table-wrap component">
          <table className="lobby-table" aria-label="Bingo game lobby">
            <thead>
              <tr>
                <th>MEDB</th>
                <th>DERASH</th>
                <th>PLAYERS</th>
                <th>STATUS</th>
                <th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {gameRows.map((row) => {
                const medbClass = MEDB_THEME[row.stake_amount] || "medb-default";
                const actionDisabled = row.action === "none";
                return (
                  <tr key={`${row.stake_amount}-${row.game_id || "new"}`}>
                    <td>
                      <span className={`medb-badge ${medbClass}`}>Br {row.stake_amount}</span>
                    </td>
                    <td className="amount-cell">{formatBirr(row.derash)}</td>
                    <td>{row.players}</td>
                    <td>
                      <span className={`status-chip status-${row.state}`}>{row.status_label}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className={`lobby-action-btn ${actionDisabled ? "disabled" : ""}`}
                        disabled={actionDisabled}
                        onClick={() => handleRowAction(row)}
                      >
                        {row.action_label}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <div className="lobby-info-actions">
          <button type="button" className="game-info-btn" onClick={() => setShowInfoModal(true)}>
            Game Information
          </button>
          <p className="lobby-sync-note">Live updates every {POLL_MS / 1000}s</p>
        </div>

        <nav className="bottom-nav" aria-label="Bottom navigation">
          <button type="button" className="bottom-nav-item active">
            <span className="bottom-nav-icon">Home</span>
            <span className="bottom-nav-label">Home</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(`/profile/${telegramId}`)}>
            <span className="bottom-nav-icon">Profile</span>
            <span className="bottom-nav-label">Profile</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => notify("error", "Top winners page coming soon.")}>
            <span className="bottom-nav-icon">Trophy</span>
            <span className="bottom-nav-label">Top Winners</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => notify("error", "Wallet page coming soon.")}>
            <span className="bottom-nav-icon">Wallet</span>
            <span className="bottom-nav-label">Wallet</span>
          </button>
        </nav>
      </div>

      {showInfoModal && (
        <div className="modal" role="dialog" aria-modal="true" aria-label="Game information">
          <div className="modal-card wide lobby-modal-card">
            <button
              type="button"
              className="modal-close"
              onClick={() => setShowInfoModal(false)}
              aria-label="Close game information"
            >
              X
            </button>
            <h2 className="component-title">Game Information</h2>
            <div className="rules-content">
              <p>How to play: Choose a game tier and join from this home page.</p>
              <p>After joining, you are redirected to the lobby page to select and manage your card.</p>
              <p>Prize calculation: DERASH = players x MEDB x 0.8.</p>
              <p>Winning condition: First player with a valid Bingo pattern wins.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
