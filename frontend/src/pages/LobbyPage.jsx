import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client.js";
import HeaderComponent from "../components/HeaderComponent.jsx";
import CardSelectionComponent from "../components/CardSelectionComponent.jsx";
import CalledNumbersComponent from "../components/CalledNumbersComponent.jsx";
import SpectatorViewComponent from "../components/SpectatorViewComponent.jsx";
import WinnerAnnouncementComponent from "../components/WinnerAnnouncementComponent.jsx";
import ActionButtonsComponent from "../components/ActionButtonsComponent.jsx";
import NotificationComponent from "../components/NotificationComponent.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };

export default function LobbyPage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
  const pollRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [finishCountdown, setFinishCountdown] = useState(null);
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
  });
  const [pendingCard, setPendingCard] = useState(null);

  const takenSet = useMemo(() => new Set(data.taken_cards), [data.taken_cards]);
  const isWatching = data.game?.state === "playing";
  const displayState = isWatching ? "watching" : data.game?.state || "waiting";

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
    if (!data.game?.id) {
      return;
    }
    pollRef.current = setInterval(() => {
      fetchJson(`/game/api/game-status/${data.game.id}/`)
        .then((payload) => {
          setData((prev) => ({
            ...prev,
            game: { ...prev.game, state: payload.state },
            total_players: payload.total_players,
            countdown: payload.countdown,
            called_numbers: payload.called_numbers,
            winner: payload.winner,
            prize_amount: payload.prize_amount,
            winner_card: payload.winner_card,
          }));
        })
        .catch(() => notify("error", "Unable to sync game state."));
    }, 2500);

    return () => clearInterval(pollRef.current);
  }, [data.game?.id]);

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  function selectCard(cardNumber) {
    setPendingCard(cardNumber);
  }

  function confirmCardSelection() {
    if (!pendingCard) {
      return;
    }
    postJson("/game/api/select-card/", {
      telegram_id: Number(telegramId),
      card_number: pendingCard,
    })
      .then((payload) => {
        if (payload.redirect_url) {
          navigate(`/play/${telegramId}/${payload.game_id || data.game.id}`);
          return;
        }
        navigate(`/play/${telegramId}/${data.game.id}`);
      })
      .catch((error) => notify("error", error.message))
      .finally(() => setPendingCard(null));
  }

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
        window.location.assign(`/lobby/${telegramId}`);
      }
    }, 1000);
    const fallback = setTimeout(() => {
      window.location.assign(`/lobby/${telegramId}`);
    }, 3500);
    return () => {
      clearInterval(timer);
      clearTimeout(fallback);
    };
  }, [data.game?.state, telegramId]);

  const stats = [
    { label: "State", value: displayState.toUpperCase() },
    { label: "Countdown", value: data.countdown || "—" },
    { label: "Players", value: data.total_players },
    { label: "Available", value: data.available_cards },
  ];

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="subtitle">Loading lobby…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="app-card">
        <HeaderComponent
          title="Bingo Lobby"
          subtitle={`Game #${data.game?.id ?? "—"} • ${data.user?.first_name ?? "Player"} • Balance ${data.wallet_balance} Birr`}
          stats={stats}
        />

        <div className="grid-layout">
          <CardSelectionComponent numbers={data.all_numbers} takenSet={takenSet} onSelect={selectCard} />
          {data.game?.state === "playing" && <CalledNumbersComponent calledNumbers={data.called_numbers || []} />}
          {data.game?.state === "playing" && <SpectatorViewComponent />}
        </div>

        <ActionButtonsComponent
          state={displayState}
          hasCard={false}
          onSelectCard={() => document.getElementById("cardSelectionComponent")?.scrollIntoView({ behavior: "smooth" })}
        />

        <NotificationComponent notification={notification} />
      </div>

      {pendingCard && (
        <div className="modal">
          <div className="modal-card">
            <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>Confirm Card</div>
            <p className="subtitle" style={{ marginTop: "8px" }}>
              Use card #{pendingCard}?
            </p>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setPendingCard(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={confirmCardSelection}>
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
      {data.game?.state === "finished" && (
        <div className="modal">
          <div className="modal-card wide">
            <WinnerAnnouncementComponent
              winnerName={data.winner}
              prizeAmount={data.prize_amount}
              winnerCard={data.winner_card}
              calledNumbers={data.called_numbers || []}
              countdown={finishCountdown}
            />
          </div>
        </div>
      )}
    </div>
  );
}
