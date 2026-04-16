import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import NotificationComponent from "../components/NotificationComponent.jsx";
import BottomNavIcon from "../components/BottomNavIcon.jsx";

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
  const countdownSeedRef = useRef({});
  const zeroSyncRef = useRef({});
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [showInfoModal, setShowInfoModal] = useState(false);
  const [displayCountdowns, setDisplayCountdowns] = useState({});
  const [data, setData] = useState({
    user: null,
    games: [],
    stakes: [10, 20, 50, 100],
    wallet_balance: 0,
  });

  const gameRows = useMemo(() => {
    if (Array.isArray(data.games) && data.games.length) {
      return data.games.map((row) => {
        const localCountdown = Number(displayCountdowns[row.stake_amount]);
        if (row.state === "waiting" && Number.isFinite(localCountdown) && localCountdown > 0) {
          return {
            ...row,
            status_label: `Starting in ${localCountdown}s`,
          };
        }
        return row;
      });
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
  }, [data.games, data.stakes, displayCountdowns]);

  const liveStats = useMemo(() => {
    const waiting = gameRows.filter((row) => row.state === "waiting").length;
    const playing = gameRows.filter((row) => row.state === "playing").length;
    return {
      waiting,
      playing,
      tiers: gameRows.length,
    };
  }, [gameRows]);

  const syncCountdownSeeds = useCallback((payload) => {
    const games = Array.isArray(payload?.games) ? payload.games : [];
    const now = Date.now();
    const nextSeeds = { ...countdownSeedRef.current };
    const activeStakes = new Set();

    setDisplayCountdowns((previous) => {
      const nextDisplay = { ...previous };

      games.forEach((row) => {
        const stake = Number(row?.stake_amount);
        if (!Number.isFinite(stake) || stake <= 0) {
          return;
        }

        activeStakes.add(stake);
        const shouldTrack = row?.state === "waiting" && Number(row?.countdown) > 0 && String(row?.status_label || "").startsWith("Starting in");
        const key = String(stake);
        const gameId = row?.game_id ?? null;

        if (!shouldTrack) {
          delete nextSeeds[key];
          delete zeroSyncRef.current[key];
          delete nextDisplay[key];
          return;
        }

        const serverCountdown = Math.max(0, Number(row.countdown) || 0);
        const seed = nextSeeds[key];
        const sameGame = seed && seed.gameId === gameId;
        const localCountdown = sameGame ? Math.max(0, seed.value - Math.floor((now - seed.startedAt) / 1000)) : null;
        const drift = localCountdown == null ? Number.POSITIVE_INFINITY : Math.abs(localCountdown - serverCountdown);
        const shouldReseed = !sameGame || localCountdown == null || serverCountdown > localCountdown || drift >= 2;

        if (shouldReseed) {
          nextSeeds[key] = { gameId, value: serverCountdown, startedAt: now };
          nextDisplay[key] = serverCountdown;
        }

        const syncState = zeroSyncRef.current[key];
        if (!syncState || syncState.gameId !== gameId) {
          zeroSyncRef.current[key] = { gameId, sent: false };
        }
      });

      Object.keys(nextSeeds).forEach((key) => {
        if (!activeStakes.has(Number(key))) {
          delete nextSeeds[key];
          delete zeroSyncRef.current[key];
          delete nextDisplay[key];
        }
      });

      return nextDisplay;
    });

    countdownSeedRef.current = nextSeeds;
  }, []);

  const syncLobbyState = useCallback(() => {
    return fetchJson(`/game/api/lobby-state/${telegramId}/`).then((payload) => {
      setData(payload);
      syncCountdownSeeds(payload);
    });
  }, [syncCountdownSeeds, telegramId]);

  useEffect(() => {
    setLoading(true);
    syncLobbyState()
      .catch((error) => notify("error", error.message))
      .finally(() => setLoading(false));
  }, [syncLobbyState]);

  useEffect(() => {
    pollRef.current = setInterval(() => {
      syncLobbyState()
        .catch(() => notify("error", "Unable to sync lobby state."));
    }, POLL_MS);

    return () => clearInterval(pollRef.current);
  }, [syncLobbyState]);

  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      setDisplayCountdowns((previous) => {
        const next = { ...previous };
        let changed = false;

        Object.entries(countdownSeedRef.current).forEach(([stakeKey, seed]) => {
          const remaining = Math.max(0, seed.value - Math.floor((now - seed.startedAt) / 1000));
          if (next[stakeKey] !== remaining) {
            next[stakeKey] = remaining;
            changed = true;
          }

          const syncState = zeroSyncRef.current[stakeKey];
          if (remaining <= 0 && syncState && !syncState.sent) {
            syncState.sent = true;
            syncLobbyState().catch(() => {
              syncState.sent = false;
            });
          }
        });

        return changed ? next : previous;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [syncLobbyState]);

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

    if ((row.action === "play" || row.action === "watch") && row.game_id && row.state === "playing") {
      navigate(withAuthPath(`/play/${telegramId}/${row.game_id}`));
      return;
    }

    navigate(withAuthPath(`/lobby/${telegramId}?stake=${stake}`));
  }

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="loading-state" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <div className="subtitle">Loading lobby...</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell lobby-shell">
      <div className="app-card lobby-card">
        <section className="component home-hero-card" aria-label="Lobby overview">
          <div className="home-hero-top">
            <div className="home-brand-row">
              <span className="home-brand-logo" role="img" aria-label="OK hand logo">👌</span>
              <h1 className="title lobby-title home-brand-title">Ok Bingo</h1>
            </div>
            <span className="home-live-chip">LIVE • {POLL_MS / 1000}s sync</span>
          </div>

          <p className="subtitle lobby-subtitle home-hero-greeting">
            Welcome back, <span className="home-hero-username">{data.user?.first_name || "Player"}</span>
          </p>

          <div className="home-wallet-highlight">
            <span className="home-wallet-label">Wallet Balance</span>
            <strong className="home-wallet-value">{formatBirr(data.wallet_balance)}</strong>
          </div>

          <div className="home-hero-chips" role="list" aria-label="Lobby quick stats">
            <span className="home-hero-chip" role="listitem">{liveStats.tiers} stake tiers</span>
            <span className="home-hero-chip" role="listitem">{liveStats.waiting} waiting</span>
            <span className="home-hero-chip" role="listitem">{liveStats.playing} in play</span>
            <span className="home-hero-chip" role="listitem">Pick a MEDB tier below</span>
          </div>
        </section>

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
                      <span
                        className={`status-chip status-${row.state}${row.state === "waiting" && Number.isFinite(Number(displayCountdowns[row.stake_amount])) && Number(displayCountdowns[row.stake_amount]) > 0 ? " countdown" : ""}`}
                      >
                        {row.state === "waiting" && Number.isFinite(Number(displayCountdowns[row.stake_amount])) && Number(displayCountdowns[row.stake_amount]) > 0
                          ? Number(displayCountdowns[row.stake_amount])
                          : row.status_label}
                      </span>
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
          <button type="button" className="game-info-btn" onClick={() => navigate(withAuthPath(`/engagement/${telegramId}`))}>
            Engagement Center
          </button>
          <p className="lobby-sync-note">Live updates every {POLL_MS / 1000}s</p>
        </div>

        <nav className="bottom-nav" aria-label="Bottom navigation">
          <button type="button" className="bottom-nav-item active">
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="home" /></span>
            <span className="bottom-nav-label">Home</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/profile/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="profile" /></span>
            <span className="bottom-nav-label">Profile</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/trophy/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="trophy" /></span>
            <span className="bottom-nav-label">Top Winners</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/wallet/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="wallet" /></span>
            <span className="bottom-nav-label">Wallet</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/engagement/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="engagement" /></span>
            <span className="bottom-nav-label">Engage</span>
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
