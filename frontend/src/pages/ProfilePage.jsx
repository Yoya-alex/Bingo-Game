import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson } from "../api/client.js";
import NotificationComponent from "../components/NotificationComponent.jsx";

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

function maskTelegramId(value) {
  const text = String(value || "");
  if (text.length <= 4) {
    return text;
  }
  return `${text.slice(0, 3)}***${text.slice(-2)}`;
}

export default function ProfilePage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [preferences, setPreferences] = useState(() => {
    try {
      const saved = window.localStorage.getItem("bingo-profile-preferences");
      if (saved) {
        return JSON.parse(saved);
      }
    } catch {
      // ignore bad local state
    }
    return {
      voiceAnnouncements: true,
      compactHistory: false,
    };
  });
  const [data, setData] = useState({
    user: null,
    wallet: null,
    stats: null,
    referrals: null,
    recent_activity: [],
    game_history: [],
  });

  useEffect(() => {
    window.localStorage.setItem("bingo-profile-preferences", JSON.stringify(preferences));
  }, [preferences]);

  useEffect(() => {
    setLoading(true);
    fetchJson(`/game/api/profile-state/${telegramId}/`)
      .then((payload) => setData(payload))
      .catch((error) => notify("error", error.message))
      .finally(() => setLoading(false));
  }, [telegramId]);

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  function togglePreference(key) {
    setPreferences((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function copyInviteCode() {
    const code = data.referrals?.invite_code;
    if (!code) {
      notify("error", "Invite code not available.");
      return;
    }
    navigator.clipboard.writeText(code)
      .then(() => notify("success", "Invite code copied."))
      .catch(() => notify("error", "Unable to copy invite code."));
  }

  const achievements = useMemo(() => {
    const stats = data.stats || {};
    const referrals = data.referrals || {};
    const items = [];

    if ((stats.wins || 0) >= 1) {
      items.push("First Win");
    }
    if ((stats.wins || 0) >= 10) {
      items.push("10 Wins Club");
    }
    if ((stats.biggest_win || 0) >= 1000) {
      items.push("Big Winner");
    }
    if ((referrals.referred_count || 0) >= 5) {
      items.push("Referral Starter");
    }
    if ((stats.games_joined || 0) >= 50) {
      items.push("Bingo Veteran");
    }

    return items.length ? items : ["No badges yet"];
  }, [data.stats, data.referrals]);

  const historyRows = preferences.compactHistory ? (data.game_history || []).slice(0, 8) : (data.game_history || []);

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="subtitle">Loading profile...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell profile-shell">
      <div className="app-card profile-card">
        <header className="profile-header component">
          <h1 className="title profile-title">Profile</h1>
          <p className="subtitle">
            {data.user?.first_name || "Player"} ({data.user?.username ? `@${data.user.username}` : "no username"})
          </p>
          <div className="profile-meta-row">
            <span>Telegram: {maskTelegramId(data.user?.telegram_id)}</span>
            <span>Joined: {formatDate(data.user?.registration_date)}</span>
          </div>
        </header>

        <NotificationComponent notification={notification} />

        <section className="component profile-section">
          <h2 className="component-title">Wallet Summary</h2>
          <div className="profile-grid profile-grid-5">
            <div className="profile-metric"><span>Total</span><strong>{formatBirr(data.wallet?.total_balance)}</strong></div>
            <div className="profile-metric"><span>Main</span><strong>{formatBirr(data.wallet?.main_balance)}</strong></div>
            <div className="profile-metric"><span>Bonus</span><strong>{formatBirr(data.wallet?.bonus_balance)}</strong></div>
            <div className="profile-metric"><span>Winnings</span><strong>{formatBirr(data.wallet?.winnings_balance)}</strong></div>
            <div className="profile-metric"><span>Withdrawable</span><strong>{formatBirr(data.wallet?.withdrawable_balance)}</strong></div>
          </div>
        </section>

        <section className="component profile-section">
          <h2 className="component-title">Game Stats</h2>
          <div className="profile-grid profile-grid-6">
            <div className="profile-metric"><span>Games Joined</span><strong>{data.stats?.games_joined || 0}</strong></div>
            <div className="profile-metric"><span>Wins</span><strong>{data.stats?.wins || 0}</strong></div>
            <div className="profile-metric"><span>Win Rate</span><strong>{Number(data.stats?.win_rate || 0).toFixed(2)}%</strong></div>
            <div className="profile-metric"><span>Total Spent</span><strong>{formatBirr(data.stats?.total_entry_spent)}</strong></div>
            <div className="profile-metric"><span>Total Won</span><strong>{formatBirr(data.stats?.total_won)}</strong></div>
            <div className="profile-metric"><span>Biggest Win</span><strong>{formatBirr(data.stats?.biggest_win)}</strong></div>
          </div>
        </section>

        <section className="component profile-section">
          <h2 className="component-title">Referrals</h2>
          <div className="profile-grid profile-grid-4">
            <div className="profile-metric"><span>Invite Code</span><strong>{data.referrals?.invite_code || "-"}</strong></div>
            <div className="profile-metric"><span>Total Referred</span><strong>{data.referrals?.referred_count || 0}</strong></div>
            <div className="profile-metric"><span>Rewarded Referrals</span><strong>{data.referrals?.rewarded_referrals || 0}</strong></div>
            <div className="profile-metric"><span>Referral Earned</span><strong>{formatBirr(data.referrals?.referral_bonus_earned)}</strong></div>
          </div>
          <div className="page-actions">
            <button type="button" className="btn btn-secondary" onClick={copyInviteCode}>Copy Invite Code</button>
          </div>
        </section>

        <section className="component profile-section">
          <h2 className="component-title">Recent Activity</h2>
          <div className="profile-table-wrap">
            {(data.recent_activity || []).length === 0 && <div className="subtitle">No transactions yet.</div>}
            {(data.recent_activity || []).length > 0 && (
              <table className="profile-table" aria-label="Recent activity table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Amount</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.recent_activity || []).map((item) => (
                    <tr key={item.id}>
                      <td>
                        <span className={`activity-type type-${item.type}`}>{item.type.replaceAll("_", " ")}</span>
                      </td>
                      <td><span className={`status-chip status-${item.status}`}>{item.status}</span></td>
                      <td>{item.amount == null ? "-" : formatBirr(item.amount)}</td>
                      <td>{formatDate(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component profile-section">
          <h2 className="component-title">Game History</h2>
          <div className="profile-table-wrap">
            {historyRows.length === 0 && <div className="subtitle">No completed games yet.</div>}
            {historyRows.length > 0 && (
              <table className="profile-table" aria-label="Game history table">
                <thead>
                  <tr>
                    <th>Game</th>
                    <th>Stake</th>
                    <th>Card</th>
                    <th>Result</th>
                    <th>Prize</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {historyRows.map((item) => (
                    <tr key={`${item.game_id}-${item.card_number}`}>
                      <td>#{item.game_id}</td>
                      <td>{item.stake_amount} Br</td>
                      <td>#{item.card_number}</td>
                      <td>
                        <span className={`history-result history-result-${item.result}`}>{item.result.toUpperCase()}</span>
                      </td>
                      <td>{item.result === "won" ? formatBirr(item.prize) : "0.00 Br"}</td>
                      <td>{formatDate(item.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component profile-section">
          <h2 className="component-title">Achievements</h2>
          <div className="badge-row">
            {achievements.map((item) => (
              <span key={item} className="medb-badge profile-badge">{item}</span>
            ))}
          </div>
        </section>

        <section className="component profile-section">
          <h2 className="component-title">Preferences</h2>
          <div className="profile-toggle-row">
            <label className="profile-toggle-item">
              <span>Voice announcements</span>
              <input type="checkbox" checked={Boolean(preferences.voiceAnnouncements)} onChange={() => togglePreference("voiceAnnouncements")} />
            </label>
            <label className="profile-toggle-item">
              <span>Compact history mode</span>
              <input type="checkbox" checked={Boolean(preferences.compactHistory)} onChange={() => togglePreference("compactHistory")} />
            </label>
          </div>
        </section>

        <section className="component profile-section">
          <h2 className="component-title">Support</h2>
          <div className="page-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => window.open("https://t.me", "_blank", "noopener,noreferrer")}
            >
              Contact Support
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => notify("success", "Issue report noted. Please contact support with details.")}
            >
              Report Issue
            </button>
          </div>
        </section>

        <nav className="bottom-nav" aria-label="Bottom navigation">
          <button type="button" className="bottom-nav-item" onClick={() => navigate(`/home/${telegramId}`)}>
            <span className="bottom-nav-icon">Home</span>
            <span className="bottom-nav-label">Home</span>
          </button>
          <button type="button" className="bottom-nav-item active">
            <span className="bottom-nav-icon">Profile</span>
            <span className="bottom-nav-label">Profile</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => notify("error", "Top winners page coming soon.")}>
            <span className="bottom-nav-icon">Trophy</span>
            <span className="bottom-nav-label">Top Winners</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => notify("error", "Wallet page coming soon.")}>
            <span className="bottom-nav-icon">Wallet</span>
            <span className="bottom-nav-label">Wallet</span>
          </button>
        </nav>
      </div>
    </div>
  );
}
