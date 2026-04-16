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

function maskTelegramId(value) {
  const text = String(value || "");
  if (text.length <= 4) {
    return text;
  }
  return `${text.slice(0, 3)}***${text.slice(-2)}`;
}

function normalizeBotUsername(raw) {
  const value = String(raw || "").trim();
  if (!value) {
    return "OK_bingobot";
  }
  return value
    .replace("https://t.me/", "")
    .replace("http://t.me/", "")
    .replace(/^@/, "")
    .replace(/\/$/, "");
}

export default function ProfilePage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [sectionNotifications, setSectionNotifications] = useState({
    referrals: EMPTY_NOTIFICATION,
    support: EMPTY_NOTIFICATION,
  });
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
    promo_claims: [],
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

  function notifySection(section, type, message) {
    setSectionNotifications((prev) => ({
      ...prev,
      [section]: { type, message },
    }));

    setTimeout(() => {
      setSectionNotifications((prev) => ({
        ...prev,
        [section]: EMPTY_NOTIFICATION,
      }));
    }, 3500);
  }

  function togglePreference(key) {
    setPreferences((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function copyInviteCode() {
    const code = data.referrals?.invite_code;
    if (!code) {
      notifySection("referrals", "error", "Invite code not available.");
      return;
    }
    const botUsername = normalizeBotUsername(import.meta.env.VITE_BOT_USERNAME || "OK_bingobot");
    const fullInviteLink = `https://t.me/${botUsername}?start=ref_${code}`;
    navigator.clipboard.writeText(fullInviteLink)
      .then(() => notifySection("referrals", "success", "Full referral link copied."))
      .catch(() => notifySection("referrals", "error", "Unable to copy invite code."));
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
          <div className="loading-state" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <div className="subtitle">Loading profile...</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell profile-shell">
      <div className="app-card profile-card">
        <header className="profile-header component">
          <h1 className="title profile-title">Profile</h1>
          <p className="subtitle profile-subtitle">
            {data.user?.first_name || "Player"} ({data.user?.username ? `@${data.user.username}` : "no username"})
          </p>
          <div className="profile-meta-row">
            <span className="profile-meta-chip">Telegram: {maskTelegramId(data.user?.telegram_id)}</span>
            <span className="profile-meta-chip">Joined: {formatDate(data.user?.registration_date)}</span>
          </div>
        </header>

        <NotificationComponent notification={notification} />

        <section className="component profile-section section-wallet">
          <h2 className="component-title">Wallet Summary</h2>
          <div className="profile-grid profile-grid-5">
            <div className="profile-metric metric-wallet-total"><span>Total</span><strong>{formatBirr(data.wallet?.total_balance)}</strong></div>
            <div className="profile-metric metric-wallet-main"><span>Main</span><strong>{formatBirr(data.wallet?.main_balance)}</strong></div>
            <div className="profile-metric metric-wallet-bonus"><span>Bonus</span><strong>{formatBirr(data.wallet?.bonus_balance)}</strong></div>
            <div className="profile-metric metric-wallet-winnings"><span>Winnings</span><strong>{formatBirr(data.wallet?.winnings_balance)}</strong></div>
            <div className="profile-metric metric-wallet-withdrawable"><span>Withdrawable</span><strong>{formatBirr(data.wallet?.withdrawable_balance)}</strong></div>
          </div>
        </section>

        <section className="component profile-section section-stats">
          <h2 className="component-title">Game Stats</h2>
          <div className="profile-grid profile-grid-6">
            <div className="profile-metric metric-stat-joined"><span>Games Joined</span><strong>{data.stats?.games_joined || 0}</strong></div>
            <div className="profile-metric metric-stat-wins"><span>Wins</span><strong>{data.stats?.wins || 0}</strong></div>
            <div className="profile-metric metric-stat-rate"><span>Win Rate</span><strong>{Number(data.stats?.win_rate || 0).toFixed(2)}%</strong></div>
            <div className="profile-metric metric-stat-spent"><span>Total Spent</span><strong>{formatBirr(data.stats?.total_entry_spent)}</strong></div>
            <div className="profile-metric metric-stat-won"><span>Total Won</span><strong>{formatBirr(data.stats?.total_won)}</strong></div>
            <div className="profile-metric metric-stat-biggest"><span>Biggest Win</span><strong>{formatBirr(data.stats?.biggest_win)}</strong></div>
          </div>
        </section>

        <section className="component profile-section section-referrals">
          <h2 className="component-title">Referrals</h2>
          {sectionNotifications.referrals?.message && (
            <div className={`notification show ${sectionNotifications.referrals.type} profile-section-notice`}>
              {sectionNotifications.referrals.message}
            </div>
          )}
          <div className="profile-grid profile-grid-4">
            <div className="profile-metric metric-ref-code"><span>Invite Code</span><strong>{data.referrals?.invite_code || "-"}</strong></div>
            <div className="profile-metric metric-ref-total"><span>Total Referred</span><strong>{data.referrals?.referred_count || 0}</strong></div>
            <div className="profile-metric metric-ref-rewarded"><span>Rewarded Referrals</span><strong>{data.referrals?.rewarded_referrals || 0}</strong></div>
            <div className="profile-metric metric-ref-earned"><span>Referral Earned</span><strong>{formatBirr(data.referrals?.referral_bonus_earned)}</strong></div>
          </div>
          <div className="page-actions">
            <button type="button" className="btn btn-secondary" onClick={copyInviteCode}>Copy Invite Code</button>
          </div>
        </section>

        <section className="component profile-section section-activity">
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

        <section className="component profile-section section-activity">
          <h2 className="component-title">Promo Claim Status</h2>
          <div className="profile-table-wrap">
            {(data.promo_claims || []).length === 0 && <div className="subtitle">No promo verification claims yet.</div>}
            {(data.promo_claims || []).length > 0 && (
              <table className="profile-table" aria-label="Promo claim status table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Status</th>
                    <th>Submitted</th>
                    <th>Decision</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.promo_claims || []).map((claim) => (
                    <tr key={claim.id}>
                      <td>{claim.promo_code}</td>
                      <td><span className={`status-chip status-${claim.status?.includes("approved") ? "completed" : claim.status?.includes("rejected") ? "rejected" : "waiting"}`}>{String(claim.status || "").replaceAll("_", " ")}</span></td>
                      <td>{formatDate(claim.submitted_at)}</td>
                      <td>{claim.decision_time ? formatDate(claim.decision_time) : "-"}</td>
                      <td>{claim.review_reason || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component profile-section section-history">
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

        <section className="component profile-section section-achievements">
          <h2 className="component-title">Achievements</h2>
          <div className="badge-row">
            {achievements.map((item) => (
              <span key={item} className="medb-badge profile-badge">{item}</span>
            ))}
          </div>
        </section>

        <section className="component profile-section section-preferences">
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

        <section className="component profile-section section-support">
          <h2 className="component-title">Support</h2>
          {sectionNotifications.support?.message && (
            <div className={`notification show ${sectionNotifications.support.type} profile-section-notice`}>
              {sectionNotifications.support.message}
            </div>
          )}
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
              onClick={() => notifySection("support", "success", "Issue report noted. Please contact support with details.")}
            >
              Report Issue
            </button>
          </div>
        </section>

        <nav className="bottom-nav" aria-label="Bottom navigation">
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/home/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="home" /></span>
            <span className="bottom-nav-label">Home</span>
          </button>
          <button type="button" className="bottom-nav-item active">
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="profile" /></span>
            <span className="bottom-nav-label">Profile</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/trophy/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="trophy" /></span>
            <span className="bottom-nav-label">Top Winners</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/wallet/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="wallet" /></span>
            <span className="bottom-nav-label">Wallet</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/engagement/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="engagement" /></span>
            <span className="bottom-nav-label">Engage</span>
          </button>
        </nav>
      </div>
    </div>
  );
}
