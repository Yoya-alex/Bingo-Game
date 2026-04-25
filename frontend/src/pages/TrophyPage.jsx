import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import NotificationComponent from "../components/NotificationComponent.jsx";
import BottomNavIcon from "../components/BottomNavIcon.jsx";
import { useI18n } from "../i18n/LanguageContext.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };

function formatBirr(value) {
  const amount = Number(value || 0);
  return `${amount.toFixed(2)} Br`;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString();
}

function playerDisplayName(row, fallbackPlayer) {
  return row?.first_name || fallbackPlayer;
}

export default function TrophyPage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [period, setPeriod] = useState("all");
  const [stake, setStake] = useState("all");
  const [data, setData] = useState({
    filters: {
      available_stakes: [10, 20, 50, 100],
      available_periods: ["today", "week", "month", "all"],
    },
    leaderboard: [],
    podium: [],
    your_position: null,
    recent_big_wins: [],
    most_active_players: [],
    refresh_time: null,
  });

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set("period", period);
    params.set("stake", stake);

    fetchJson(`/game/api/trophy-state/${telegramId}/?${params.toString()}`)
      .then((payload) => setData(payload))
      .catch((error) => notify("error", error.message))
      .finally(() => setLoading(false));
  }, [telegramId, period, stake]);

  const yourRow = data.your_position || {};
  const leaderboard = data.leaderboard || [];
  const podiumByRank = useMemo(() => {
    const bucket = new Map();
    (data.podium || []).forEach((row) => {
      bucket.set(Number(row.rank), row);
    });
    return bucket;
  }, [data.podium]);

  const periodOptions = useMemo(() => data.filters?.available_periods || ["today", "week", "month", "all"], [data.filters]);
  const stakeOptions = useMemo(() => ["all", ...(data.filters?.available_stakes || [10, 20, 50, 100])], [data.filters]);
  const renderPodiumCard = (rank) => {
    const row = podiumByRank.get(rank);
    if (!row) {
      return null;
    }
    return (
      <div className={`trophy-podium-card rank-${rank}`}>
        <div className="trophy-cup" aria-hidden="true">
          <span className="trophy-cup-bowl" />
          <span className="trophy-cup-stem" />
          <span className="trophy-cup-base" />
        </div>
        <div className="trophy-rank">#{rank}</div>
        <div className="trophy-name">{playerDisplayName(row, t("common.player"))}</div>
        <div className="trophy-value">{formatBirr(row.total_winnings)}</div>
        <small>{t("trophy.winsCount", { count: row.wins })}</small>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="loading-state" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <div className="subtitle">{t("trophy.loading")}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell trophy-shell">
      <div className="app-card trophy-card">
        <header className="component trophy-header">
          <h1 className="title trophy-title">{t("trophy.title")}</h1>
          <p className="subtitle">{t("trophy.leaderboardRefresh")}: {formatDate(data.refresh_time)}</p>
          {data.filters?.period === "season" && data.filters?.season_name && (
            <p className="subtitle">{t("trophy.season")}: {data.filters.season_name}</p>
          )}
        </header>

        <NotificationComponent notification={notification} />

        <section className="component trophy-filters">
          <h2 className="component-title">{t("trophy.filters")}</h2>
          <div className="trophy-filter-row">
            {periodOptions.map((option) => (
              <button
                key={option}
                type="button"
                className={`trophy-filter-chip ${period === option ? "active" : ""}`}
                onClick={() => setPeriod(option)}
              >
                {t(`trophy.period.${option}`)}
              </button>
            ))}
          </div>
          <div className="trophy-filter-row">
            {stakeOptions.map((option) => {
              const isActive = String(stake) === String(option);
              const label = option === "all" ? t("trophy.allStakes") : `${option} Br`;
              return (
                <button
                  key={String(option)}
                  type="button"
                  className={`trophy-filter-chip stake ${isActive ? "active" : ""}`}
                  onClick={() => setStake(String(option))}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </section>

        <section className="component trophy-podium">
          <h2 className="component-title">{t("trophy.podium")}</h2>
          {!data.podium?.length && <div className="subtitle">{t("trophy.noWinnersForFilter")}</div>}
          {!!data.podium?.length && (
            <div className="trophy-podium-stage" aria-label={t("trophy.top3PodiumAria")}>
              <div className="trophy-podium-slot podium-slot-1">
                {renderPodiumCard(1)}
              </div>
              <div className="trophy-podium-slot podium-slot-2">
                {renderPodiumCard(2)}
              </div>
              <div className="trophy-podium-slot podium-slot-3">
                {renderPodiumCard(3)}
              </div>
            </div>
          )}
        </section>

        <section className="component trophy-your-position">
          <h2 className="component-title">{t("trophy.yourPosition")}</h2>
          <div className="profile-grid profile-grid-6">
            <div className="profile-metric trophy-pos-rank"><span>{t("trophy.rank")}</span><strong>{yourRow.rank || "-"}</strong></div>
            <div className="profile-metric trophy-pos-total"><span>{t("profile.totalWon")}</span><strong>{formatBirr(yourRow.total_winnings)}</strong></div>
            <div className="profile-metric trophy-pos-wins"><span>{t("profile.wins")}</span><strong>{yourRow.wins || 0}</strong></div>
            <div className="profile-metric trophy-pos-games"><span>{t("trophy.games")}</span><strong>{yourRow.games_joined || 0}</strong></div>
            <div className="profile-metric trophy-pos-rate"><span>{t("profile.winRate")}</span><strong>{Number(yourRow.win_rate || 0).toFixed(2)}%</strong></div>
            <div className="profile-metric trophy-pos-gap"><span>{t("trophy.gapToNext")}</span><strong>{yourRow.gap_to_next_rank == null ? "-" : formatBirr(yourRow.gap_to_next_rank)}</strong></div>
          </div>
        </section>

        <section className="component trophy-leaderboard">
          <h2 className="component-title">{t("trophy.leaderboard")}</h2>
          <div className="profile-table-wrap">
            {leaderboard.length === 0 && <div className="subtitle">{t("trophy.noLeaderboardData")}</div>}
            {leaderboard.length > 0 && (
              <table className="profile-table" aria-label={t("trophy.leaderboardAria")}>
                <thead>
                  <tr>
                    <th>{t("trophy.rank")}</th>
                    <th>{t("common.player")}</th>
                    <th>{t("profile.totalWon")}</th>
                    <th>{t("profile.wins")}</th>
                    <th>{t("trophy.games")}</th>
                    <th>{t("profile.winRate")}</th>
                    <th>{t("trophy.seasonPts")}</th>
                    <th>{t("profile.biggestWin")}</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.map((row) => (
                    <tr key={row.user_id} className={row.user_id === yourRow.user_id ? "trophy-self-row" : ""}>
                      <td className="trophy-cell-rank">#{row.rank}</td>
                      <td className="trophy-cell-player">{playerDisplayName(row, t("common.player"))}</td>
                      <td className="trophy-cell-money">{formatBirr(row.total_winnings)}</td>
                      <td className="trophy-cell-success">{row.wins}</td>
                      <td className="trophy-cell-active">{row.games_joined}</td>
                      <td className="trophy-cell-rate">{Number(row.win_rate || 0).toFixed(2)}%</td>
                      <td className="trophy-cell-active">{row.season_points ?? "-"}</td>
                      <td className="trophy-cell-jackpot">{formatBirr(row.biggest_win)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component trophy-recent-wins">
          <h2 className="component-title">{t("trophy.recentBigWins")}</h2>
          <div className="profile-table-wrap">
            {(data.recent_big_wins || []).length === 0 && <div className="subtitle">{t("trophy.noBigWins")}</div>}
            {(data.recent_big_wins || []).length > 0 && (
              <table className="profile-table" aria-label={t("trophy.recentBigWinsAria")}>
                <thead>
                  <tr>
                    <th>{t("common.game")}</th>
                    <th>{t("trophy.winner")}</th>
                    <th>{t("profile.stake")}</th>
                    <th>{t("common.prize")}</th>
                    <th>{t("wallet.date")}</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.recent_big_wins || []).map((row) => (
                    <tr key={`${row.game_id}-${row.finished_at}`}>
                      <td>#{row.game_id}</td>
                      <td className="trophy-cell-player">{row.winner_name || t("common.player")}</td>
                      <td className="trophy-cell-stake">{row.stake_amount} Br</td>
                      <td className="trophy-cell-jackpot">{formatBirr(row.prize_amount)}</td>
                      <td>{formatDate(row.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component trophy-most-active">
          <h2 className="component-title">{t("trophy.mostActivePlayers")}</h2>
          <div className="profile-table-wrap">
            {(data.most_active_players || []).length === 0 && <div className="subtitle">{t("trophy.noActivityData")}</div>}
            {(data.most_active_players || []).length > 0 && (
              <table className="profile-table" aria-label={t("trophy.mostActivePlayersAria")}>
                <thead>
                  <tr>
                    <th>{t("common.player")}</th>
                    <th>{t("profile.gamesJoined")}</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.most_active_players || []).map((row) => (
                    <tr key={row.user_id}>
                      <td className="trophy-cell-player">{playerDisplayName(row, t("common.player"))}</td>
                      <td className="trophy-cell-active">{row.games_joined}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <nav className="bottom-nav" aria-label={t("profile.bottomNavigationAria")}>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/home/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="home" /></span>
            <span className="bottom-nav-label">{t("common.home")}</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/profile/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="profile" /></span>
            <span className="bottom-nav-label">{t("common.profile")}</span>
          </button>
          <button type="button" className="bottom-nav-item active">
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
