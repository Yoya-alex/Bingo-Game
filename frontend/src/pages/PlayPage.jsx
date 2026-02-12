import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client.js";
import HeaderComponent from "../components/HeaderComponent.jsx";
import BingoGridComponent from "../components/BingoGridComponent.jsx";
import CalledNumbersComponent from "../components/CalledNumbersComponent.jsx";
import SpectatorViewComponent from "../components/SpectatorViewComponent.jsx";
import WinnerAnnouncementComponent from "../components/WinnerAnnouncementComponent.jsx";
import ActionButtonsComponent from "../components/ActionButtonsComponent.jsx";
import NotificationComponent from "../components/NotificationComponent.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };

export default function PlayPage() {
  const { telegramId, gameId } = useParams();
  const pollRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [state, setState] = useState({
    user: null,
    game: null,
    card: null,
    called_numbers: [],
    total_players: 0,
    prize_amount: 0,
    winner: null,
    countdown: 0,
  });

  const calledNumbers = state.called_numbers || [];
  const hasCard = Boolean(state.card?.card_number);

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
      fetchJson(`/game/api/game-status/${state.game.id}/`)
        .then((payload) => {
          setState((prev) => ({
            ...prev,
            game: { ...prev.game, state: payload.state },
            total_players: payload.total_players,
            called_numbers: payload.called_numbers,
            prize_amount: payload.prize_amount,
            winner: payload.winner,
            countdown: payload.countdown,
          }));
        })
        .catch(() => notify("error", "Unable to sync game state."));
    }, 2500);

    return () => clearInterval(pollRef.current);
  }, [state.game?.id]);

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
          }));
          return;
        }
        notify("error", payload.message);
      })
      .catch((error) => notify("error", error.message));
  }

  const stats = useMemo(() => {
    const lastThree = calledNumbers.slice(-3).reverse();
    return [
      { label: "State", value: state.game?.state?.toUpperCase() || "—" },
      { label: "Countdown", value: state.countdown || "—" },
      { label: "Players", value: state.total_players },
      { label: "Current Call", value: lastThree[0] || "—" },
      { label: "Last 3", value: lastThree.join(" ") || "—" },
    ];
  }, [calledNumbers, state.game?.state, state.total_players, state.countdown]);

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="subtitle">Loading game…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="app-card">
        <HeaderComponent
          title="Bingo Arena"
          subtitle={`Game #${state.game.id} • Card #${state.card.card_number} • ${state.user.first_name}`}
          stats={stats}
        />

        <div className="grid-layout">
          {hasCard && <BingoGridComponent grid={state.card.grid} calledNumbers={calledNumbers} />}
          <CalledNumbersComponent calledNumbers={calledNumbers} />
          {!hasCard && state.game?.state === "playing" && <SpectatorViewComponent />}
          {state.game?.state === "finished" && (
            <WinnerAnnouncementComponent winnerName={state.winner} prizeAmount={state.prize_amount} />
          )}
        </div>

        <ActionButtonsComponent state={state.game?.state} hasCard={hasCard} onBingo={claimBingo} />
        <NotificationComponent notification={notification} />
      </div>
    </div>
  );
}
