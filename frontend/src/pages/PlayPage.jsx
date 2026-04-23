import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import BingoGridComponent from "../components/BingoGridComponent.jsx";
import CalledNumbersComponent from "../components/CalledNumbersComponent.jsx";
import SpectatorViewComponent from "../components/SpectatorViewComponent.jsx";
import WinnerAnnouncementComponent from "../components/WinnerAnnouncementComponent.jsx";
import ActionButtonsComponent from "../components/ActionButtonsComponent.jsx";
import NotificationComponent from "../components/NotificationComponent.jsx";
import VoiceSyncManager from "../utils/voiceSyncManager.js";
import { useI18n } from "../i18n/LanguageContext.jsx";
import { useSettings } from "../context/SettingsContext.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };

export default function PlayPage() {
  const { telegramId, gameId } = useParams();
  const navigate = useNavigate();
  const pollRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [finishCountdown, setFinishCountdown] = useState(null);
  const [voiceSupported, setVoiceSupported] = useState(true);
  const [autoPlayEnabled, setAutoPlayEnabled] = useState(false);
  const voiceManagerRef = useRef(null);
  const lastAutoMarkRef = useRef(null);
  const [state, setState] = useState({
    user: null,
    game: null,
    card: null,
    marked_numbers: [],
    called_numbers: [],
    server_time: null,
    number_call_interval: 0,
    bingo_number_max: 400,
    total_players: 0,
    prize_amount: 0,
    winner: null,
    winner_card: null,
    countdown: 0,
  });
  const { t } = useI18n();
  const { voiceEnabled } = useSettings();

  const calledNumberEntries = state.called_numbers || [];
  const calledNumbers = useMemo(
    () => calledNumberEntries.map((entry) => Number(entry?.number)).filter((value) => Number.isFinite(value)),
    [calledNumberEntries]
  );
  const markedNumbers = state.marked_numbers || [];
  const currentCall = calledNumbers.length ? calledNumbers[calledNumbers.length - 1] : null;
  const hasCard = Boolean(state.card?.card_number);
  const displayState = !hasCard && state.game?.state === "playing" ? "watching" : state.game?.state;
  const shouldConfirmQuit = state.game?.state === "playing" && hasCard;
  const currentCallParts = useMemo(() => {
    if (!Number.isFinite(currentCall)) {
      return null;
    }

    const limit = Math.max(5, Number(state.bingo_number_max) || 400);
    const step = Math.max(1, Math.floor(limit / 5));
    const letters = ["B", "I", "N", "G", "O"];
    const index = Math.min(4, Math.max(0, Math.floor((currentCall - 1) / step)));
    return { letter: letters[index], number: currentCall };
  }, [currentCall, state.bingo_number_max]);

  const derashAmount = useMemo(() => {
    const stakeAmount = Number(state.game?.stake_amount || 10);
    const value = state.total_players * stakeAmount * 0.8;
    return `${new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)} Birr`;
  }, [state.total_players, state.game?.stake_amount]);

  useEffect(() => {
    setLoading(true);
    fetchJson(`/game/api/play-state/${telegramId}/${gameId}/`)
      .then((payload) => {
        setState(payload);
      })
      .catch((error) => notify("error", error.message))
      .finally(() => setLoading(false));
  }, [telegramId, gameId]);

  useEffect(() => {
    if (!state.game?.id) {
      return;
    }
    pollRef.current = setInterval(() => {
      fetchJson(`/game/api/play-state/${telegramId}/${gameId}/`)
        .then((payload) => setState(payload))
        .catch(() => notify("error", t("play.syncFailed")));
    }, 2500);

    return () => clearInterval(pollRef.current);
  }, [state.game?.id, telegramId, gameId, t]);

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  function claimBingo() {
    postJson("/game/api/claim-bingo/", {
      telegram_id: Number(telegramId),
      game_id: Number(gameId),
    })
      .then((payload) => {
        if (payload.winner) {
          notify("success", payload.message);
          setState((prev) => ({
            ...prev,
            game: { ...prev.game, state: "finished" },
            winner: prev.user?.first_name || "You",
            prize_amount: payload.prize,
            winner_card: payload.winner_card || {
              card_number: prev.card?.card_number,
              grid: prev.card?.grid,
            },
          }));
          return;
        }
        notify("error", payload.message);
      })
      .catch((error) => notify("error", error.message));
  }

  function markCurrentNumber(number) {
    if (!hasCard || state.game?.state !== "playing") {
      return;
    }
    if (!calledNumbers.some((called) => Number(called) === Number(number))) {
      return;
    }
    postJson("/game/api/mark-number/", {
      telegram_id: Number(telegramId),
      game_id: Number(gameId),
      number,
    })
      .then((payload) => {
        setState((prev) => ({
          ...prev,
          marked_numbers: payload.marked_numbers || prev.marked_numbers,
        }));
      })
      .catch((error) => notify("error", error.message));
  }

  function handleBackToHome() {
    if (shouldConfirmQuit) {
      const confirmed = window.confirm(t("play.quitConfirm"));
      if (!confirmed) {
        return;
      }
    }
    navigate(withAuthPath(`/home/${telegramId}`));
  }

  useEffect(() => {
    voiceManagerRef.current = new VoiceSyncManager();
    setVoiceSupported(voiceManagerRef.current.supported);
    return () => {
      voiceManagerRef.current?.destroy();
      voiceManagerRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!voiceManagerRef.current) {
      return;
    }

    if (!voiceSupported) {
      voiceManagerRef.current.setEnabled(false);
      return;
    }

    voiceManagerRef.current.setEnabled(voiceEnabled);
  }, [voiceEnabled, voiceSupported]);

  useEffect(() => {
    if (!voiceManagerRef.current) {
      return;
    }

    const result = voiceManagerRef.current.processUpdate({
      state: state.game?.state,
      calledNumbers: calledNumberEntries,
      serverTime: state.server_time,
      callIntervalSeconds: state.number_call_interval,
      maxNumber: state.bingo_number_max,
    });

    if (result?.status === "unsupported") {
      setVoiceSupported(false);
    }
  }, [state.game?.state, calledNumberEntries, state.server_time, state.number_call_interval, state.bingo_number_max]);

  useEffect(() => {
    if (state.game?.state !== "finished") {
      setFinishCountdown(null);
      return;
    }
    let remaining = 3;
    setFinishCountdown(remaining);
    const timer = setInterval(() => {
      remaining -= 1;
      setFinishCountdown(remaining);
      if (remaining <= 0) {
        clearInterval(timer);
        window.location.assign(withAuthPath(`/lobby/${telegramId}`));
      }
    }, 1000);
    const fallback = setTimeout(() => {
      window.location.assign(withAuthPath(`/lobby/${telegramId}`));
    }, 3500);
    return () => {
      clearInterval(timer);
      clearTimeout(fallback);
    };
  }, [state.game?.state, telegramId]);

  useEffect(() => {
    if (!shouldConfirmQuit) {
      return undefined;
    }

    const handlePopState = () => {
      const confirmed = window.confirm(t("play.quitConfirm"));
      if (confirmed) {
        window.location.assign(withAuthPath(`/home/${telegramId}`));
        return;
      }
      window.history.pushState({ guard: "play-page" }, "", window.location.href);
    };

    window.history.pushState({ guard: "play-page" }, "", window.location.href);
    window.addEventListener("popstate", handlePopState);

    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, [shouldConfirmQuit, telegramId, t]);

  // Check if a set of marked numbers forms a winning bingo pattern on the grid
  function checkBingoWin(grid, markedSet) {
    const SIZE = 5;
    // rows
    for (let r = 0; r < SIZE; r++) {
      if (grid[r].every((cell) => cell === null || markedSet.has(Number(cell)))) return true;
    }
    // columns
    for (let c = 0; c < SIZE; c++) {
      if (grid.every((row) => row[c] === null || markedSet.has(Number(row[c])))) return true;
    }
    // main diagonal
    if (grid.every((row, i) => row[i] === null || markedSet.has(Number(row[i])))) return true;
    // anti diagonal
    if (grid.every((row, i) => row[SIZE - 1 - i] === null || markedSet.has(Number(row[SIZE - 1 - i])))) return true;
    return false;
  }

  useEffect(() => {
    if (!autoPlayEnabled || !hasCard || state.game?.state !== "playing") {
      return;
    }

    const grid = state.card?.grid;
    if (!grid?.length) return;

    const gridNumbers = grid.flat().filter((value) => value != null);
    if (!gridNumbers.length) return;

    const gridSet = new Set(gridNumbers.map((value) => Number(value)));
    const markedSet = new Set(markedNumbers.map((v) => Number(v)));

    // Mark all called numbers on the card that haven't been marked yet
    const unmarkedCalled = calledNumbers.filter(
      (value) => gridSet.has(Number(value)) && !markedSet.has(Number(value))
    );

    if (unmarkedCalled.length > 0) {
      const nextNumber = unmarkedCalled[unmarkedCalled.length - 1];
      if (lastAutoMarkRef.current !== nextNumber) {
        lastAutoMarkRef.current = nextNumber;
        markCurrentNumber(nextNumber);
      }
      return;
    }

    // All callable numbers are marked — check for a win
    if (checkBingoWin(grid, markedSet)) {
      claimBingo();
    }
  }, [autoPlayEnabled, calledNumbers, hasCard, markedNumbers, state.game?.state, state.card?.grid]);

  const stats = useMemo(() => {
    return [
      { label: t("common.players"), value: state.total_players },
      { label: t("common.medeb"), value: `${state.game?.stake_amount || 10} Birr` },
      { label: t("common.derash"), value: derashAmount },
      { label: t("common.called"), value: calledNumbers.length ? `${calledNumbers.length}/75` : "-" },
    ];
  }, [calledNumbers, state.total_players, derashAmount, t, state.game?.stake_amount]);

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="loading-state" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <div className="subtitle">{t("common.loadingGame")}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell play-page">
      <div className="app-card">
        <div className="play-top-row">
          <div className="page-actions">
            <button type="button" className="btn btn-secondary play-back-btn" onClick={handleBackToHome}>
              Back
            </button>
          </div>
          <div className="home-brand-row play-brand-row">
            <span className="home-brand-logo" role="img" aria-label={t("home.okHandLogoAria")}>👌</span>
            <h1 className="title lobby-title home-brand-title">{t("home.brand")}</h1>
          </div>
        </div>

        <div className="component stat-strip">
          {stats.map((stat) => (
            <div className="stat-item" key={stat.label}>
              <span>{stat.label}</span>
              <div className="stat-value">{stat.value}</div>
            </div>
          ))}
        </div>

        <NotificationComponent notification={notification} />
        <div className="grid-layout">
          <div className="called-numbers-stack">
            <div className="stat-strip current-call play-current-strip">
              <div className="stat-item current-call-item">
                <div className="stat-value current-call-value">
                  {currentCallParts ? (
                    <span className="call-badge">
                      <span className="call-letter">{currentCallParts.letter}</span>
                      <span className="call-value">{currentCallParts.number}</span>
                    </span>
                  ) : (
                    "-"
                  )}
                </div>
              </div>
            </div>
            <CalledNumbersComponent
              calledNumbers={calledNumbers}
              maxNumber={state.bingo_number_max || 400}
              onNumberClick={markCurrentNumber}
              interactive={hasCard && state.game?.state === "playing"}
            />
          </div>
          {hasCard && (
            <div className="bingo-stack">
              <div className="auto-play-toggle">
                <button
                  type="button"
                  className={`auto-play-btn${autoPlayEnabled ? " is-on" : ""}`}
                  onClick={() => setAutoPlayEnabled((prev) => !prev)}
                  role="switch"
                  aria-checked={autoPlayEnabled}
                >
                  <span className="auto-play-label">{autoPlayEnabled ? "Automatic" : "Manual"}</span>
                  <span className="auto-play-track" aria-hidden="true">
                    <span className="auto-play-thumb" />
                  </span>
                </button>
              </div>
              <BingoGridComponent
                grid={state.card.grid}
                calledNumbers={calledNumbers}
                markedNumbers={markedNumbers}
                markSource="marked"
                interactive={state.game?.state === "playing"}
                clickableNumber={state.game?.state === "playing" ? currentCall : null}
                onSelectNumber={markCurrentNumber}
                footer={
                  <ActionButtonsComponent
                    state={displayState}
                    hasCard={hasCard}
                    onBingo={claimBingo}
                    bingoLabel={autoPlayEnabled ? "AUTOMATIC" : undefined}
                  />
                }
              />
            </div>
          )}
          {!hasCard && state.game?.state === "playing" && (
            <SpectatorViewComponent id="bingoGridComponent" title={t("play.yourBingoGrid")} />
          )}
        </div>
      </div>
      {state.game?.state === "finished" && (
        <div className="modal">
          <div className="modal-card wide">
            <WinnerAnnouncementComponent
              winnerName={state.winner}
              prizeAmount={state.prize_amount}
              winnerCard={state.winner_card}
              calledNumbers={calledNumbers}
              countdown={finishCountdown}
            />
          </div>
        </div>
      )}
    </div>
  );
}
