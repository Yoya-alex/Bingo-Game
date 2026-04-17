import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import HeaderComponent from "../components/HeaderComponent.jsx";
import BingoGridComponent from "../components/BingoGridComponent.jsx";
import CalledNumbersComponent from "../components/CalledNumbersComponent.jsx";
import SpectatorViewComponent from "../components/SpectatorViewComponent.jsx";
import WinnerAnnouncementComponent from "../components/WinnerAnnouncementComponent.jsx";
import ActionButtonsComponent from "../components/ActionButtonsComponent.jsx";
import NotificationComponent from "../components/NotificationComponent.jsx";
import VoiceSyncManager from "../utils/voiceSyncManager.js";
import { useI18n } from "../i18n/LanguageContext.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };

export default function PlayPage() {
  const { telegramId, gameId } = useParams();
  const navigate = useNavigate();
  const pollRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [finishCountdown, setFinishCountdown] = useState(null);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(true);
  const voiceManagerRef = useRef(null);
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

  const formatCalledNumber = useMemo(() => {
    const maxNumber = Math.max(5, Number(state.bingo_number_max) || 400);
    const step = Math.max(1, Math.floor(maxNumber / 5));
    const letters = ["B", "I", "N", "G", "O"];

    return (value) => {
      const number = Number(value);
      if (!Number.isFinite(number)) {
        return "—";
      }
      const index = Math.min(4, Math.max(0, Math.floor((number - 1) / step)));
      return `${letters[index]}${number}`;
    };
  }, [state.bingo_number_max]);

  const derashAmount = useMemo(() => {
    const stakeAmount = Number(state.game?.stake_amount || 10);
    const value = state.total_players * stakeAmount * 0.8;
    return `${new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)} Birr`;
  }, [state.total_players, state.game?.stake_amount]);

  function toCallParts(value) {
    const formatted = String(formatCalledNumber(value));
    const match = formatted.match(/^([A-Za-z]+)(\d+)$/);
    if (match) {
      return { letter: match[1].toUpperCase(), number: match[2] };
    }
    return { letter: "#", number: formatted };
  }

  function renderCallBadge(value, keyPrefix) {
    if (value == null) {
      return "—";
    }
    const parts = toCallParts(value);
    return (
      <span key={`${keyPrefix}-${value}`} className="call-badge">
        <span className="call-letter">{parts.letter}</span>
        <span className="call-value">{parts.number}</span>
      </span>
    );
  }

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

  function toggleVoiceAssistant() {
    if (!voiceSupported) {
      notify("error", t("play.voiceUnsupported"));
      return;
    }
    setVoiceEnabled((prev) => !prev);
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
    voiceManagerRef.current.setEnabled(voiceEnabled);
  }, [voiceEnabled]);

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

  const stats = useMemo(() => {
    return [
      { label: t("common.state"), value: displayState?.toUpperCase() || "—" },
      { label: t("common.players"), value: state.total_players },
      {label:t("common.medeb"), value: `${state.game?.stake_amount || 10} Birr`},
      { label: t("common.derash"), value: derashAmount },
      {label:t("common.called"), value: calledNumbers.length ? `${calledNumbers.length}/75` : "-"},
    ];
  }, [calledNumbers, displayState, state.total_players, derashAmount, t, state.game?.stake_amount]);

  const voiceStateClass = !voiceSupported ? "voice-unsupported" : voiceEnabled ? "voice-on" : "voice-off";
  const voiceButtonTitle = !voiceSupported ? t("play.voiceUnsupportedShort") : voiceEnabled ? t("play.voiceOn") : t("play.voiceOff");
  const showVoiceToggle = voiceSupported && state.game?.state === "playing";

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
    <div className="app-shell">
      {showVoiceToggle && (
        <button
          className={`theme-toggle voice-toggle voice-icon-btn ${voiceStateClass}`}
          onClick={toggleVoiceAssistant}
          aria-label={voiceButtonTitle}
          title={voiceButtonTitle}
        >
          <span className="voice-icon" aria-hidden="true">🔊</span>
        </button>
      )}
      <div className="app-card">
        <HeaderComponent
          title={t("play.title")}
          subtitle={`${t("common.game")} #${state.game?.id ?? "-"} • ${hasCard ? `${t("common.card")} #${state.card.card_number} • ` : `${t("common.spectator")} • `}${state.user?.first_name ?? t("common.player")}`}
          stats={stats}
        />

        {state.game?.state !== "finished" && (
          <div className="stat-strip current-call" style={{ marginTop: "10px" }}>
            <div className="stat-item current-call-item">
              <span className="current-call-label">{t("common.currentCall")}</span>
              <div className="stat-value current-call-value">{renderCallBadge(currentCall, "current")}</div>
            </div>
          </div>
        )}
        <NotificationComponent notification={notification} />
        <div className="page-actions">
          <button type="button" className="btn btn-secondary" onClick={handleBackToHome}>
            {t("common.backToHome")}
          </button>
        </div>
        <div className="grid-layout">
          {hasCard && (
            <BingoGridComponent
              grid={state.card.grid}
              calledNumbers={calledNumbers}
              markedNumbers={markedNumbers}
              markSource="marked"
              interactive={state.game?.state === "playing"}
              clickableNumber={state.game?.state === "playing" ? currentCall : null}
              onSelectNumber={markCurrentNumber}
              footer={<ActionButtonsComponent state={displayState} hasCard={hasCard} onBingo={claimBingo} />}
              
            />
            
            
          )
          }
          {!hasCard && state.game?.state === "playing" && (
            <SpectatorViewComponent id="bingoGridComponent" title={t("play.yourBingoGrid")} />
          )}
          <CalledNumbersComponent 
            calledNumbers={calledNumbers} 
            maxNumber={state.bingo_number_max || 400}
            onNumberClick={markCurrentNumber}
            interactive={hasCard && state.game?.state === "playing"}
          />
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
