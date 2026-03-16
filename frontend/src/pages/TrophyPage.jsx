import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import NotificationComponent from "../components/NotificationComponent.jsx";
import BottomNavIcon from "../components/BottomNavIcon.jsx";

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

function playerDisplayName(row) {
  return row?.first_name || "Player";
}

export default function TrophyPage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
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
    tie_break_rules: [],
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
        <div className="trophy-name">{playerDisplayName(row)}</div>
        <div className="trophy-value">{formatBirr(row.total_winnings)}</div>
        <small>{row.wins} wins</small>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="subtitle">Loading trophy board...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell trophy-shell">
      <div className="app-card trophy-card">
        <header className="component trophy-header">
          <h1 className="title trophy-title">Top Winners</h1>
          <p className="subtitle">Leaderboard refresh: {formatDate(data.refresh_time)}</p>
        </header>

        <NotificationComponent notification={notification} />

        <section className="component trophy-filters">
          <h2 className="component-title">Filters</h2>
          <div className="trophy-filter-row">
            {periodOptions.map((option) => (
              <button
                key={option}
                type="button"
                className={`trophy-filter-chip ${period === option ? "active" : ""}`}
                onClick={() => setPeriod(option)}
              >
                {option.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="trophy-filter-row">
            {stakeOptions.map((option) => {
              const isActive = String(stake) === String(option);
              const label = option === "all" ? "ALL STAKES" : `${option} Br`;
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
          <h2 className="component-title">Podium</h2>
          {!data.podium?.length && <div className="subtitle">No winners found for this filter.</div>}
          {!!data.podium?.length && (
            <div className="trophy-podium-stage" aria-label="Top 3 podium">
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
          <h2 className="component-title">Your Position</h2>
          <div className="profile-grid profile-grid-6">
            <div className="profile-metric trophy-pos-rank"><span>Rank</span><strong>{yourRow.rank || "-"}</strong></div>
            <div className="profile-metric trophy-pos-total"><span>Total Won</span><strong>{formatBirr(yourRow.total_winnings)}</strong></div>
            <div className="profile-metric trophy-pos-wins"><span>Wins</span><strong>{yourRow.wins || 0}</strong></div>
            <div className="profile-metric trophy-pos-games"><span>Games</span><strong>{yourRow.games_joined || 0}</strong></div>
            <div className="profile-metric trophy-pos-rate"><span>Win Rate</span><strong>{Number(yourRow.win_rate || 0).toFixed(2)}%</strong></div>
            <div className="profile-metric trophy-pos-gap"><span>Gap To Next</span><strong>{yourRow.gap_to_next_rank == null ? "-" : formatBirr(yourRow.gap_to_next_rank)}</strong></div>
          </div>
        </section>

        <section className="component trophy-leaderboard">
          <h2 className="component-title">Leaderboard</h2>
          <div className="profile-table-wrap">
            {leaderboard.length === 0 && <div className="subtitle">No leaderboard data yet.</div>}
            {leaderboard.length > 0 && (
              <table className="profile-table" aria-label="Top winners leaderboard table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Player</th>
                    <th>Total Won</th>
                    <th>Wins</th>
                    <th>Games</th>
                    <th>Win Rate</th>
                    <th>Biggest Win</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboard.map((row) => (
                    <tr key={row.user_id} className={row.user_id === yourRow.user_id ? "trophy-self-row" : ""}>
                      <td className="trophy-cell-rank">#{row.rank}</td>
                      <td className="trophy-cell-player">{playerDisplayName(row)}</td>
                      <td className="trophy-cell-money">{formatBirr(row.total_winnings)}</td>
                      <td className="trophy-cell-success">{row.wins}</td>
                      <td className="trophy-cell-active">{row.games_joined}</td>
                      <td className="trophy-cell-rate">{Number(row.win_rate || 0).toFixed(2)}%</td>
                      <td className="trophy-cell-jackpot">{formatBirr(row.biggest_win)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component trophy-recent-wins">
          <h2 className="component-title">Recent Big Wins</h2>
          <div className="profile-table-wrap">
            {(data.recent_big_wins || []).length === 0 && <div className="subtitle">No big wins in this filter.</div>}
            {(data.recent_big_wins || []).length > 0 && (
              <table className="profile-table" aria-label="Recent big wins table">
                <thead>
                  <tr>
                    <th>Game</th>
                    <th>Winner</th>
                    <th>Stake</th>
                    <th>Prize</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.recent_big_wins || []).map((row) => (
                    <tr key={`${row.game_id}-${row.finished_at}`}>
                      <td>#{row.game_id}</td>
                      <td className="trophy-cell-player">{row.winner_name || "Player"}</td>
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
          <h2 className="component-title">Most Active Players</h2>
          <div className="profile-table-wrap">
            {(data.most_active_players || []).length === 0 && <div className="subtitle">No activity data for this filter.</div>}
            {(data.most_active_players || []).length > 0 && (
              <table className="profile-table" aria-label="Most active players table">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th>Games Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.most_active_players || []).map((row) => (
                    <tr key={row.user_id}>
                      <td className="trophy-cell-player">{playerDisplayName(row)}</td>
                      <td className="trophy-cell-active">{row.games_joined}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component trophy-rules">
          <h2 className="component-title">Tie-Break Rules</h2>
          <div className="rules-content">
            {(data.tie_break_rules || []).map((rule) => (
              <p key={rule}>{rule}</p>
            ))}
          </div>
        </section>

        <nav className="bottom-nav" aria-label="Bottom navigation">
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/home/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="home" /></span>
            <span className="bottom-nav-label">Home</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/profile/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="profile" /></span>
            <span className="bottom-nav-label">Profile</span>
          </button>
          <button type="button" className="bottom-nav-item active">
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="trophy" /></span>
            <span className="bottom-nav-label">Top Winners</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/wallet/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="wallet" /></span>
            <span className="bottom-nav-label">Wallet</span>
          </button>
        </nav>
      </div>
    </div>
  );
}
