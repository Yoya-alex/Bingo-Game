import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import NotificationComponent from "../components/NotificationComponent.jsx";
import BottomNavIcon from "../components/BottomNavIcon.jsx";
import { useI18n } from "../i18n/LanguageContext.jsx";

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
  const [activeGuideIndex, setActiveGuideIndex] = useState(0);
  const [displayCountdowns, setDisplayCountdowns] = useState({});
  const [data, setData] = useState({
    user: null,
    games: [],
    stakes: [10, 20, 50, 100],
    wallet_balance: 0,
  });
  const { t } = useI18n();

  const gameRows = useMemo(() => {
    if (Array.isArray(data.games) && data.games.length) {
      return data.games.map((row) => {
        const localCountdown = Number(displayCountdowns[row.stake_amount]);
        if (row.state === "waiting" && Number.isFinite(localCountdown) && localCountdown > 0) {
          return {
            ...row,
            status_label: t("home.startsIn", { seconds: localCountdown }),
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
      status_label: t("home.waitingPlayers"),
      state: "waiting",
      action: "join",
      action_label: t("common.selectCard"),
      user_has_card: false,
    }));
  }, [data.games, data.stakes, displayCountdowns, t]);

  const liveStats = useMemo(() => {
    const waiting = gameRows.filter((row) => row.state === "waiting").length;
    const playing = gameRows.filter((row) => row.state === "playing").length;
    return {
      waiting,
      playing,
      tiers: gameRows.length,
    };
  }, [gameRows]);

  const featuredGame = useMemo(() => {
    const rows = Array.isArray(gameRows) ? gameRows : [];
    if (!rows.length) {
      return null;
    }

    const playing = rows.filter((row) => row.state === "playing");
    if (playing.length) {
      return playing.sort((a, b) => Number(b.players || 0) - Number(a.players || 0))[0];
    }

    const waiting = rows.filter((row) => row.state === "waiting");
    if (waiting.length) {
      return waiting.sort((a, b) => Number(b.players || 0) - Number(a.players || 0))[0];
    }

    return rows[0];
  }, [gameRows]);

  const infoContext = useMemo(() => {
    const row = featuredGame;
    if (!row) {
      return {
        statusLabel: t("common.waiting"),
        state: "waiting",
        stake: 0,
        players: 0,
        derash: 0,
        countdown: 0,
      };
    }

    const localCountdown = Number(displayCountdowns[row.stake_amount]);
    const countdown = row.state === "waiting"
      ? (Number.isFinite(localCountdown) && localCountdown > 0 ? localCountdown : Math.max(0, Number(row.countdown || 0)))
      : 0;

    return {
      statusLabel: row.state === "playing" ? t("home.liveRound") : countdown > 0 ? t("home.startsIn", { seconds: countdown }) : t("home.waitingPlayers"),
      state: row.state,
      stake: Number(row.stake_amount || 0),
      players: Number(row.players || 0),
      derash: Number(row.derash || 0),
      countdown,
    };
  }, [displayCountdowns, featuredGame, t]);

  const previewCard = useMemo(() => {
    const seed = Number(featuredGame?.game_id || featuredGame?.stake_amount || 17);
    const ranges = [
      [1, 15],
      [16, 30],
      [31, 45],
      [46, 60],
      [61, 75],
    ];

    const makeColumn = (start, end, offset) => {
      const values = [];
      for (let n = start; n <= end; n += 1) {
        values.push(n);
      }
      for (let i = values.length - 1; i > 0; i -= 1) {
        const j = (seed + offset + i * 7) % (i + 1);
        const temp = values[i];
        values[i] = values[j];
        values[j] = temp;
      }
      return values.slice(0, 5);
    };

    const cols = ranges.map(([start, end], idx) => makeColumn(start, end, idx * 13));
    const matrix = Array.from({ length: 5 }, (_, rowIdx) => cols.map((col) => col[rowIdx]));
    matrix[2][2] = "FREE";
    return matrix;
  }, [featuredGame]);

  const guidePatterns = useMemo(
    () => [
      { type: "row", index: 0 },
      { type: "row", index: 1 },
      { type: "row", index: 2 },
      { type: "row", index: 3 },
      { type: "row", index: 4 },
      { type: "col", index: 0 },
      { type: "col", index: 1 },
      { type: "col", index: 2 },
      { type: "col", index: 3 },
      { type: "col", index: 4 },
      { type: "diag", index: 0 },
      { type: "diag", index: 1 },
    ],
    [],
  );

  const activeGuidePattern = guidePatterns[activeGuideIndex] || guidePatterns[0];

  function isWinningPreviewCell(cellIndex, pattern) {
    if (!pattern) {
      return false;
    }

    const row = Math.floor(cellIndex / 5);
    const col = cellIndex % 5;

    if (pattern.type === "row") {
      return row === pattern.index;
    }
    if (pattern.type === "col") {
      return col === pattern.index;
    }
    if (pattern.type === "diag") {
      if (pattern.index === 0) {
        return row === col;
      }
      return row + col === 4;
    }
    return false;
  }

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
    const patternTimer = setInterval(() => {
      setActiveGuideIndex((prev) => (prev + 1) % guidePatterns.length);
    }, 1400);
    return () => clearInterval(patternTimer);
  }, [guidePatterns.length]);

  useEffect(() => {
    pollRef.current = setInterval(() => {
      syncLobbyState()
        .catch(() => notify("error", t("lobby.syncFailed")));
    }, POLL_MS);

    return () => clearInterval(pollRef.current);
  }, [syncLobbyState, t]);

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
      notify("error", t("home.invalidGameTier"));
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
            <div className="subtitle">{t("common.loadingLobby")}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell lobby-shell">
      <div className="app-card lobby-card">
        <section className="component home-hero-card" aria-label={t("home.lobbyOverviewAria")}>
          <div className="home-hero-top">
            <div className="home-brand-row">
              <span className="home-brand-logo" role="img" aria-label={t("home.okHandLogoAria")}>👌</span>
              <h1 className="title lobby-title home-brand-title">{t("home.brand")}</h1>
            </div>
            <span className="home-live-chip">{t("home.liveChip", { seconds: POLL_MS / 1000 })}</span>
          </div>

          <p className="subtitle lobby-subtitle home-hero-greeting">
            {t("home.welcomeBack", { name: data.user?.first_name || t("common.player") })}
          </p>

          <div className="home-wallet-highlight">
            <span className="home-wallet-label">{t("home.walletBalance")}</span>
            <strong className="home-wallet-value">{formatBirr(data.wallet_balance)}</strong>
          </div>

          <div className="home-hero-chips" role="list" aria-label={t("home.quickStatsAria")}>
            <span className="home-hero-chip" role="listitem">{t("home.stakeTiers", { count: liveStats.tiers })}</span>
            <span className="home-hero-chip" role="listitem">{t("home.waitingCount", { count: liveStats.waiting })}</span>
            <span className="home-hero-chip" role="listitem">{t("home.inPlayCount", { count: liveStats.playing })}</span>
            <span className="home-hero-chip" role="listitem">{t("home.pickTier")}</span>
          </div>
        </section>

        <NotificationComponent notification={notification} />

        <section className="lobby-table-wrap component">
          <table className="lobby-table" aria-label={t("home.bingoLobbyAria")}>
            <thead>
              <tr>
                <th>{t("home.medb")}</th>
                <th>{t("home.derash")}</th>
                <th>{t("home.players")}</th>
                <th>{t("home.status")}</th>
                <th>{t("home.action")}</th>
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
          <p className="lobby-sync-note">{t("home.liveUpdatesEvery", { seconds: POLL_MS / 1000 })}</p>
        </div>

        <section className="component home-game-info-section" aria-label={t("home.gameInfoDialogAria")}>
          <h2 className="component-title">{t("home.gameInfoTitle")}</h2>
          <div className="game-info-live-grid">
            <section className="game-info-panel card-panel" aria-label={t("home.cardWinGuideAria")}>
              <div className="bingo-preview-header">
                <h3>{t("home.winningPreview")}</h3>
                <p>{t("home.animatedBoxes")}</p>
              </div>
              <div className="bingo-preview-card-wrap">
                <div className="bingo-preview-card" role="img" aria-label={t("home.previewCardAria")}>
                  <div className="bingo-preview-labels">
                    {['B', 'I', 'N', 'G', 'O'].map((letter) => (
                      <span key={letter}>{letter}</span>
                    ))}
                  </div>
                  <div className="bingo-preview-grid">
                    {previewCard.flat().map((value, index) => (
                      <div
                        key={`${index}-${String(value)}`}
                        className={`bingo-preview-cell ${value === "FREE" ? "free" : ""} ${isWinningPreviewCell(index, activeGuidePattern) ? "win-guide-active" : ""}`}
                      >
                        {value}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            <section className="game-info-panel" aria-label={t("home.currentSnapshotAria")}>
              <div className="game-info-status-row">
                <span className={`status-chip status-${infoContext.state}`}>{infoContext.statusLabel}</span>
                <span className="game-info-live-pill">{t("home.liveSync")}</span>
              </div>
              <div className="game-info-metrics">
                <article className="game-info-metric-card">
                  <span>{t("home.roundStatus")}</span>
                  <strong>{infoContext.state === "playing" ? t("common.playing") : t("common.waiting")}</strong>
                </article>
                <article className="game-info-metric-card">
                  <span>{t("home.activePlayers")}</span>
                  <strong>{infoContext.players}</strong>
                </article>
                <article className="game-info-metric-card">
                  <span>{t("home.medb")}</span>
                  <strong>{formatBirr(infoContext.stake)}</strong>
                </article>
                <article className="game-info-metric-card">
                  <span>{t("home.currentDerash")}</span>
                  <strong>{formatBirr(infoContext.derash)}</strong>
                </article>
                <article className="game-info-metric-card wide">
                  <span>{t("home.countdown")}</span>
                  <strong>{infoContext.state === "waiting" ? `${infoContext.countdown}s` : t("common.roundInProgress")}</strong>
                </article>
              </div>
              <div className="rules-content game-info-rules">
                <p>{t("home.chooseTier")}</p>
                <p>{t("home.firstPlayerWins")}</p>
                <p>{t("home.winLines")}</p>
              </div>
            </section>
          </div>
        </section>

        <nav className="bottom-nav" aria-label={t("profile.bottomNavigationAria")}>
          <button type="button" className="bottom-nav-item active">
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="home" /></span>
            <span className="bottom-nav-label">{t("common.home")}</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/profile/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="profile" /></span>
            <span className="bottom-nav-label">{t("common.profile")}</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/trophy/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="trophy" /></span>
            <span className="bottom-nav-label">{t("common.topWinners")}</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/wallet/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="wallet" /></span>
            <span className="bottom-nav-label">{t("common.wallet")}</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/engagement/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="engagement" /></span>
            <span className="bottom-nav-label">{t("common.engage")}</span>
          </button>
        </nav>
      </div>

    </div>
  );
}
