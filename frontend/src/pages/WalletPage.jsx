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

function formatLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function WalletPage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [data, setData] = useState({
    user: null,
    wallet: null,
    overview: null,
    finance_summary: null,
    filters: {
      types: ["all"],
      statuses: ["all"],
    },
    recent_transactions: [],
    informational_notes: [],
  });

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set("type", typeFilter);
    params.set("status", statusFilter);

    fetchJson(`/game/api/wallet-state/${telegramId}/?${params.toString()}`)
      .then((payload) => setData(payload))
      .catch((error) => notify("error", error.message))
      .finally(() => setLoading(false));
  }, [telegramId, typeFilter, statusFilter]);

  const transactionRows = useMemo(() => data.recent_transactions || [], [data.recent_transactions]);

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="subtitle">Loading wallet insights...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell profile-shell">
      <div className="app-card profile-card wallet-card">
        <header className="component profile-header wallet-header">
          <h1 className="title profile-title wallet-title">Wallet</h1>
          <p className="subtitle profile-subtitle wallet-subtitle">
            {data.user?.first_name || "Player"} - Last wallet update {formatDate(data.wallet?.updated_at)}
          </p>
        </header>

        <NotificationComponent notification={notification} />

        <section className="component profile-section section-wallet wallet-section">
          <h2 className="component-title">Balance Snapshot</h2>
          <div className="profile-grid profile-grid-5">
            <div className="profile-metric metric-wallet-total"><span>Total</span><strong>{formatBirr(data.wallet?.total_balance)}</strong></div>
            <div className="profile-metric metric-wallet-main"><span>Main</span><strong>{formatBirr(data.wallet?.main_balance)}</strong></div>
            <div className="profile-metric metric-wallet-bonus"><span>Bonus</span><strong>{formatBirr(data.wallet?.bonus_balance)}</strong></div>
            <div className="profile-metric metric-wallet-winnings"><span>Winnings</span><strong>{formatBirr(data.wallet?.winnings_balance)}</strong></div>
            <div className="profile-metric metric-wallet-withdrawable"><span>Withdrawable</span><strong>{formatBirr(data.wallet?.withdrawable_balance)}</strong></div>
          </div>
        </section>

        <section className="component profile-section section-activity wallet-section-overview">
          <h2 className="component-title">Transaction Overview</h2>
          <div className="profile-grid profile-grid-5">
            <div className="profile-metric wallet-metric-total"><span>Total Transactions</span><strong>{data.overview?.total_transactions || 0}</strong></div>
            <div className="profile-metric wallet-metric-pending"><span>Pending</span><strong>{data.overview?.pending_transactions || 0}</strong></div>
            <div className="profile-metric wallet-metric-completed"><span>Completed</span><strong>{data.overview?.completed_transactions || 0}</strong></div>
            <div className="profile-metric wallet-metric-rejected"><span>Rejected</span><strong>{data.overview?.rejected_transactions || 0}</strong></div>
            <div className="profile-metric wallet-metric-last"><span>Last Activity</span><strong className="wallet-last-activity">{formatDate(data.overview?.last_transaction_at)}</strong></div>
          </div>
        </section>

        <section className="component profile-section section-stats wallet-section-finance">
          <h2 className="component-title">Game Finance Summary</h2>
          <div className="profile-grid profile-grid-6">
            <div className="profile-metric metric-stat-spent"><span>Total Entry Spent</span><strong>{formatBirr(data.finance_summary?.total_entry_spent)}</strong></div>
            <div className="profile-metric metric-stat-won"><span>Total Won</span><strong>{formatBirr(data.finance_summary?.total_game_won)}</strong></div>
            <div className="profile-metric wallet-metric-referral"><span>Referral Bonus</span><strong>{formatBirr(data.finance_summary?.total_referral_bonus)}</strong></div>
            <div className="profile-metric wallet-metric-net"><span>Net P/L</span><strong>{formatBirr(data.finance_summary?.net_profit_loss)}</strong></div>
            <div className="profile-metric metric-stat-biggest"><span>Biggest Win</span><strong>{formatBirr(data.finance_summary?.biggest_win)}</strong></div>
            <div className="profile-metric wallet-metric-today"><span>Today Net</span><strong>{formatBirr(data.finance_summary?.today_net)}</strong></div>
            <div className="profile-metric wallet-metric-month"><span>30-Day Net</span><strong>{formatBirr(data.finance_summary?.month_net)}</strong></div>
          </div>
        </section>

        <section className="component profile-section section-history wallet-section-transactions">
          <h2 className="component-title">Recent Transactions</h2>
          <div className="trophy-filter-row">
            {(data.filters?.types || ["all"]).map((option) => (
              <button
                key={`type-${option}`}
                type="button"
                className={`trophy-filter-chip ${typeFilter === option ? "active" : ""}`}
                onClick={() => setTypeFilter(option)}
              >
                {formatLabel(option)}
              </button>
            ))}
          </div>
          <div className="trophy-filter-row">
            {(data.filters?.statuses || ["all"]).map((option) => (
              <button
                key={`status-${option}`}
                type="button"
                className={`trophy-filter-chip stake ${statusFilter === option ? "active" : ""}`}
                onClick={() => setStatusFilter(option)}
              >
                {formatLabel(option)}
              </button>
            ))}
          </div>

          <div className="profile-table-wrap">
            {transactionRows.length === 0 && <div className="subtitle">No transactions found for current filters.</div>}
            {transactionRows.length > 0 && (
              <table className="profile-table" aria-label="Wallet transactions table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Amount</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {transactionRows.map((item) => (
                    <tr key={item.id}>
                      <td><span className={`activity-type type-${item.type}`}>{formatLabel(item.type)}</span></td>
                      <td><span className={`status-chip status-${item.status}`}>{formatLabel(item.status)}</span></td>
                      <td className={item.amount != null && Number(item.amount) >= 0 ? "wallet-amount-positive" : "wallet-amount-negative"}>
                        {item.amount == null ? "-" : formatBirr(item.amount)}
                      </td>
                      <td>{formatDate(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component profile-section section-support wallet-section-info">
          <h2 className="component-title">Wallet Notes</h2>
          <div className="rules-content">
            {(data.informational_notes || []).map((note) => (
              <p key={note}>{note}</p>
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
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/trophy/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="trophy" /></span>
            <span className="bottom-nav-label">Top Winners</span>
          </button>
          <button type="button" className="bottom-nav-item active">
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
