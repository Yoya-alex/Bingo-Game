import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import CardSelectionComponent from "../components/CardSelectionComponent.jsx";
import BingoGridComponent from "../components/BingoGridComponent.jsx";
import CalledNumbersComponent from "../components/CalledNumbersComponent.jsx";
import SpectatorViewComponent from "../components/SpectatorViewComponent.jsx";
import WinnerAnnouncementComponent from "../components/WinnerAnnouncementComponent.jsx";
import NotificationComponent from "../components/NotificationComponent.jsx";
import { useI18n } from "../i18n/LanguageContext.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };

function normalizeLobbyPayload(payload, preferredStake) {
  const games = Array.isArray(payload?.games) ? payload.games : [];
  const selectedGame = payload?.selected_game || null;
  const fallbackRow =
    games.find((row) => Number(row.stake_amount) === Number(preferredStake)) || games[0] || null;

  if (selectedGame) {
    const takenCards = selectedGame.taken_cards || [];
    return {
      user: payload.user || null,
      game: {
        id: selectedGame.id,
        state: selectedGame.state,
      },
      wallet_balance: payload.wallet_balance || 0,
      taken_cards: takenCards,
      all_numbers: payload.all_numbers || [],
      total_players: selectedGame.total_players || 0,
      available_cards: selectedGame.available_cards ?? Math.max((payload.all_numbers || []).length - takenCards.length, 0),
      stake: selectedGame.stake_amount || preferredStake,
      countdown: selectedGame.countdown || 0,
      called_numbers: selectedGame.called_numbers || [],
      winner: selectedGame.winner || null,
      prize_amount: selectedGame.prize_amount ?? selectedGame.derash ?? 0,
      winner_card: selectedGame.winner_card || null,
      user_card: selectedGame.user_card || null,
    };
  }

  const takenCards = fallbackRow?.taken_cards || [];
  return {
    user: payload?.user || null,
    game: {
      id: fallbackRow?.game_id || null,
      state: fallbackRow?.state || "waiting",
    },
    wallet_balance: payload?.wallet_balance || 0,
    taken_cards: takenCards,
    all_numbers: payload?.all_numbers || [],
    total_players: fallbackRow?.players || 0,
    available_cards: fallbackRow?.available_cards ?? Math.max((payload?.all_numbers || []).length - takenCards.length, 0),
    stake: fallbackRow?.stake_amount || preferredStake,
    countdown: fallbackRow?.countdown || 0,
    called_numbers: [],
    winner: null,
    prize_amount: fallbackRow?.derash || 0,
    winner_card: null,
    user_card: null,
  };
}

export default function LobbyPage() {
  const { telegramId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const lobbyPollRef = useRef(null);
  const countdownSeedRef = useRef({ gameId: null, value: 0, startedAt: 0 });
  const zeroSyncRef = useRef({ gameId: null, sent: false });
  const preferredStake = Number(searchParams.get("stake")) || 10;
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [finishCountdown, setFinishCountdown] = useState(null);
  const [isSelecting, setIsSelecting] = useState(false);
  const [displayCountdown, setDisplayCountdown] = useState(0);
  const [data, setData] = useState({
    user: null,
    game: null,
    wallet_balance: 0,
    taken_cards: [],
    all_numbers: [],
    total_players: 0,
    available_cards: 0,
    stake: 0,
    countdown: 0,
    called_numbers: [],
    winner: null,
    prize_amount: 0,
    winner_card: null,
    user_card: null,
  });
  const { t } = useI18n();



  const selectedCardNumber = data.user_card?.card_number ?? null;
  const takenSet = useMemo(() => {
    const taken = data.taken_cards.filter((num) => num !== selectedCardNumber);
    return new Set(taken);
  }, [data.taken_cards, selectedCardNumber]);
  const hasCard = Boolean(selectedCardNumber);
  const isWatching = data.game?.state === "playing" && !hasCard;
  const displayState = isWatching ? "watching" : data.game?.state || "waiting";
  const calledNumbers = useMemo(
    () => (data.called_numbers || []).map((entry) => Number(entry?.number)).filter((value) => Number.isFinite(value)),
    [data.called_numbers]
  );
  const shouldConfirmQuit = data.game?.state === "playing" && hasCard;

  const syncCountdownSeed = useCallback((nextData) => {
    const gameId = nextData.game?.id ?? null;
    const state = nextData.game?.state;
    const serverCountdown = Math.max(0, Number(nextData.countdown) || 0);

    if (state !== "waiting" || !gameId) {
      countdownSeedRef.current = { gameId: null, value: 0, startedAt: 0 };
      zeroSyncRef.current = { gameId: null, sent: false };
      setDisplayCountdown(0);
      return;
    }

    const now = Date.now();
    const seed = countdownSeedRef.current;
    const sameGame = seed.gameId === gameId;
    const localCountdown = sameGame ? Math.max(0, seed.value - Math.floor((now - seed.startedAt) / 1000)) : null;
    const drift = localCountdown == null ? Number.POSITIVE_INFINITY : Math.abs(localCountdown - serverCountdown);
    const shouldReseed = !sameGame || localCountdown == null || serverCountdown > localCountdown || drift >= 2;

    if (shouldReseed) {
      countdownSeedRef.current = { gameId, value: serverCountdown, startedAt: now };
      setDisplayCountdown(serverCountdown);
    }

    if (zeroSyncRef.current.gameId !== gameId) {
      zeroSyncRef.current = { gameId, sent: false };
    }
  }, []);

  const syncLobbyState = useCallback(() => {
    return fetchJson(`/game/api/lobby-state/${telegramId}/`).then((payload) => {
      const normalized = normalizeLobbyPayload(payload, preferredStake);
      setData(normalized);
      syncCountdownSeed(normalized);
    });
  }, [preferredStake, syncCountdownSeed, telegramId]);

  useEffect(() => {
    setLoading(true);
    syncLobbyState()
      .catch((error) => notify("error", error.message))
      .finally(() => setLoading(false));
  }, [telegramId, preferredStake]);

  useEffect(() => {
    lobbyPollRef.current = setInterval(() => {
      syncLobbyState()
        .catch(() => notify("error", t("lobby.syncFailed")));
    }, 2500);

    return () => clearInterval(lobbyPollRef.current);
  }, [syncLobbyState, t]);

  useEffect(() => {
    const timer = setInterval(() => {
      const seed = countdownSeedRef.current;
      if (!seed.gameId) {
        return;
      }

      const remaining = Math.max(0, seed.value - Math.floor((Date.now() - seed.startedAt) / 1000));
      setDisplayCountdown((prev) => (prev === remaining ? prev : remaining));

      if (remaining <= 0 && data.game?.state === "waiting" && data.game?.id) {
        if (zeroSyncRef.current.gameId === data.game.id && !zeroSyncRef.current.sent) {
          zeroSyncRef.current.sent = true;
          syncLobbyState().catch(() => {
            zeroSyncRef.current.sent = false;
          });
        }
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [data.game?.id, data.game?.state, syncLobbyState]);

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  function selectCard(cardNumber) {
    if (data.game?.state === "playing") {
      notify("error", t("lobby.cardSelectionClosed"));
      return;
    }
    
    // Check if user has sufficient balance
    const requiredBalance = data.stake || preferredStake;
    if (data.wallet_balance < requiredBalance) {
      notify("error", t("lobby.insufficientBalance", { amount: requiredBalance }));
      return;
    }
    
    if (isSelecting) {
      return;
    }
    setIsSelecting(true);
    postJson("/game/api/select-card/", {
      telegram_id: Number(telegramId),
      card_number: cardNumber,
      stake_amount: data.stake || preferredStake,
    })
      .then(() => syncLobbyState())
      .catch((error) => notify("error", error.message))
      .finally(() => setIsSelecting(false));
  }

  function handleBackToHome() {
    if (shouldConfirmQuit) {
      const confirmed = window.confirm(t("lobby.quitConfirm"));
      if (!confirmed) {
        return;
      }
    }
    navigate(withAuthPath(`/home/${telegramId}`));
  }

  useEffect(() => {
    if (data.game?.state === "playing" && data.game?.id) {
      navigate(withAuthPath(`/play/${telegramId}/${data.game.id}`));
    }
  }, [data.game?.state, data.game?.id, navigate, telegramId]);

  useEffect(() => {
    if (data.game?.state !== "finished") {
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
  }, [data.game?.state, telegramId]);

  const countdownValue = displayState === "waiting" && displayCountdown > 0 ? displayCountdown : "-";
  const showCountdownBox = Boolean(data.user_card?.grid) && displayState === "waiting" && displayCountdown > 0;

  const stats = [
    { label: "Derash", value: `${data.stake || preferredStake} Birr` },
    { label: t("common.walletBalance"), value: `${data.wallet_balance || 0} Birr` },
    { label: t("common.players"), value: data.total_players },
    { label: t("common.medeb"), value: `${data.stake || preferredStake} Birr` },
  ];

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
    <div className="app-shell lobby-page">
      <div className="app-card">
        <div className="page-actions">
          <button type="button" className="btn btn-secondary lobby-back-btn" onClick={handleBackToHome}>
            Back
          </button>
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
          {data.user_card?.grid && (
            <>
              {showCountdownBox && (
                <section className="component lobby-countdown-box is-active" aria-live="polite" aria-atomic="true">
                  <div className="lobby-countdown-message" key={countdownValue}>
                    <span className="lobby-countdown-text">The game starting in</span>
                    <span className="lobby-countdown-clock" aria-hidden="true">⏰</span>
                    <span className="lobby-countdown-seconds">{countdownValue}</span>
                    <span className="lobby-countdown-text">seconds</span>
                  </div>
                </section>
              )}
              <BingoGridComponent grid={data.user_card.grid} interactive={false} />
            </>
          )}
          {data.game?.state !== "playing" && (
            <CardSelectionComponent
              numbers={data.all_numbers}
              takenSet={takenSet}
              selectedNumber={selectedCardNumber}
              onSelect={selectCard}
            />
          )}
          {data.game?.state === "playing" && <CalledNumbersComponent calledNumbers={calledNumbers} maxNumber={400} />}
          {data.game?.state === "playing" && <SpectatorViewComponent />}
        </div>

        <NotificationComponent notification={notification} />
      </div>

      {data.game?.state === "finished" && (
        <div className="modal">
          <div className="modal-card wide">
            <WinnerAnnouncementComponent
              winnerName={data.winner}
              prizeAmount={data.prize_amount}
              winnerCard={data.winner_card}
              calledNumbers={calledNumbers}
              countdown={finishCountdown}
            />
          </div>
        </div>
      )}
    </div>
  );
}
