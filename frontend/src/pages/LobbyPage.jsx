import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client.js";
import HeaderComponent from "../components/HeaderComponent.jsx";
import CardSelectionComponent from "../components/CardSelectionComponent.jsx";
import BingoGridComponent from "../components/BingoGridComponent.jsx";
import CalledNumbersComponent from "../components/CalledNumbersComponent.jsx";
import SpectatorViewComponent from "../components/SpectatorViewComponent.jsx";
import WinnerAnnouncementComponent from "../components/WinnerAnnouncementComponent.jsx";
import ActionButtonsComponent from "../components/ActionButtonsComponent.jsx";
import NotificationComponent from "../components/NotificationComponent.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };

export default function LobbyPage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
  const lobbyPollRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [finishCountdown, setFinishCountdown] = useState(null);
  const [isSelecting, setIsSelecting] = useState(false);
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
    lobbyPollRef.current = setInterval(() => {
      fetchJson(`/game/api/lobby-state/${telegramId}/`)
        .then((payload) => setData(payload))
        .catch(() => notify("error", "Unable to sync lobby state."));
    }, 2500);

    return () => clearInterval(lobbyPollRef.current);
  }, [telegramId]);

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  function selectCard(cardNumber) {
    if (data.game?.state === "playing") {
      notify("error", "Card selection is closed for this round.");
      return;
    }
    if (isSelecting) {
      return;
    }
    setIsSelecting(true);
    postJson("/game/api/select-card/", {
      telegram_id: Number(telegramId),
      card_number: cardNumber,
    })
      .then(() => fetchJson(`/game/api/lobby-state/${telegramId}/`))
      .then((statePayload) => setData(statePayload))
      .catch((error) => notify("error", error.message))
      .finally(() => setIsSelecting(false));
  }

  useEffect(() => {
    if (data.game?.state === "playing" && hasCard) {
      navigate(`/play/${telegramId}/${data.game.id}`);
    }
  }, [data.game?.state, data.game?.id, hasCard, navigate, telegramId]);

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
    { label: "Count", value: data.countdown || "—" },
    { label: "Players", value: data.total_players },
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
        
        <NotificationComponent notification={notification} />

        <div className="grid-layout">
          {data.user_card?.grid && <BingoGridComponent grid={data.user_card.grid} interactive={false} />}
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

        <ActionButtonsComponent
          state={displayState}
          hasCard={hasCard}
          onSelectCard={() => document.getElementById("cardSelectionComponent")?.scrollIntoView({ behavior: "smooth" })}
        />

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
