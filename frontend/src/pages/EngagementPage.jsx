import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import NotificationComponent from "../components/NotificationComponent.jsx";
import BottomNavIcon from "../components/BottomNavIcon.jsx";

const EMPTY_NOTIFICATION = { type: "", message: "" };
const EMPTY_PROMO_OVERLAY = { show: false, type: "", message: "" };

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

function formatTitle(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function EngagementPage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [promoCodeInput, setPromoCodeInput] = useState("");
  const [notification, setNotification] = useState(EMPTY_NOTIFICATION);
  const [promoOverlay, setPromoOverlay] = useState(EMPTY_PROMO_OVERLAY);
  const [missionData, setMissionData] = useState({ missions: [], streak: null, server_time: null });
  const [promoData, setPromoData] = useState({ promo_codes: [], server_time: null });
  const [eventData, setEventData] = useState({ active_events: [], upcoming_events: [], server_time: null });

  function notify(type, message) {
    setNotification({ type, message });
    setTimeout(() => setNotification(EMPTY_NOTIFICATION), 3500);
  }

  function showPromoOverlay(type, message) {
    setPromoOverlay({ show: true, type, message });
    setTimeout(() => setPromoOverlay(EMPTY_PROMO_OVERLAY), 2200);
  }

  async function loadAll() {
    const [missions, promos, events] = await Promise.all([
      fetchJson(`/game/api/missions-state/${telegramId}/`),
      fetchJson(`/game/api/promo-codes/${telegramId}/`),
      fetchJson(`/game/api/live-events/${telegramId}/`),
    ]);

    setMissionData(missions);
    setPromoData(promos);
    setEventData(events);
  }

  useEffect(() => {
    setLoading(true);
    loadAll()
      .catch((error) => notify("error", error.message))
      .finally(() => setLoading(false));
  }, [telegramId]);

  const claimableMissions = useMemo(
    () => (missionData.missions || []).filter((mission) => mission.is_completed && !mission.is_claimed),
    [missionData.missions],
  );

  async function redeemPromo(code) {
    const promoCode = (code || promoCodeInput || "").trim().toUpperCase();
    if (!promoCode) {
      notify("error", "Enter a promo code first.");
      return;
    }

    setBusy(true);
    try {
      const payload = await postJson("/game/api/redeem-promo-code/", {
        telegram_id: Number(telegramId),
        code: promoCode,
      });
      showPromoOverlay("success", `Promo redeemed: ${payload.code} • +${formatBirr(payload.credited_amount)}`);
      setPromoCodeInput("");
      await loadAll();
    } catch (error) {
      showPromoOverlay("error", error.message);
    } finally {
      setBusy(false);
    }
  }

  async function claimMission(progressId) {
    setBusy(true);
    try {
      const payload = await postJson("/game/api/claim-mission/", {
        telegram_id: Number(telegramId),
        progress_id: progressId,
      });
      notify("success", `Mission claimed: +${formatBirr(payload.reward_amount)}`);
      await loadAll();
    } catch (error) {
      notify("error", error.message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="app-shell">
        <div className="app-card">
          <div className="subtitle">Loading engagement center...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell profile-shell">
      <div className="app-card profile-card engagement-card">
        <header className="component profile-header engagement-header">
          <h1 className="title profile-title">Engagement Center</h1>
          <p className="subtitle profile-subtitle">
            Missions, promo rewards, and live events in one place.
          </p>
        </header>

        <NotificationComponent notification={notification} />

        {promoOverlay.show && (
          <div className="engagement-overlay" role="status" aria-live="polite">
            <div className={`engagement-overlay-card ${promoOverlay.type}`}>
              <h3>{promoOverlay.type === "success" ? "Promo Applied" : "Promo Unavailable"}</h3>
              <p>{promoOverlay.message}</p>
            </div>
          </div>
        )}

        <section className="component profile-section section-engagement-streak">
          <h2 className="component-title">Daily Streak</h2>
          <div className="profile-grid profile-grid-4">
            <div className="profile-metric"><span>Current Streak</span><strong>{missionData.streak?.current_streak || 0}</strong></div>
            <div className="profile-metric"><span>Best Streak</span><strong>{missionData.streak?.best_streak || 0}</strong></div>
            <div className="profile-metric"><span>Streak Protect</span><strong>{missionData.streak?.streak_protect_tokens || 0}</strong></div>
            <div className="profile-metric"><span>Last Active</span><strong>{missionData.streak?.last_active_date || "-"}</strong></div>
          </div>
        </section>

        <section className="component profile-section section-engagement-missions">
          <h2 className="component-title">Missions</h2>
          {claimableMissions.length > 0 && (
            <div className="engagement-claim-banner">
              {claimableMissions.length} mission reward(s) ready to claim
            </div>
          )}
          <div className="profile-table-wrap">
            {(missionData.missions || []).length === 0 && <div className="subtitle">No active missions yet.</div>}
            {(missionData.missions || []).length > 0 && (
              <table className="profile-table" aria-label="Missions table">
                <thead>
                  <tr>
                    <th>Mission</th>
                    <th>Period / Progress</th>
                    <th>Reward / Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {(missionData.missions || []).map((mission) => {
                    const progressText = `${mission.progress_value}/${mission.target_value}`;
                    const canClaim = mission.is_completed && !mission.is_claimed;
                    return (
                      <tr key={mission.progress_id}>
                        <td>
                          <strong>{mission.title}</strong>
                          <div className="wallet-note-inline">{mission.description || formatTitle(mission.mission_type)}</div>
                        </td>
                        <td>
                          <div>{formatTitle(mission.period)}</div>
                          <div className="wallet-note-inline">{progressText}</div>
                        </td>
                        <td>
                          <div>
                            {formatBirr(mission.reward_amount)}
                            <span className={`engagement-balance-chip balance-${mission.reward_balance}`}>
                              {formatTitle(mission.reward_balance)}
                            </span>
                          </div>
                          <div className="wallet-note-inline">
                            {mission.is_claimed ? (
                              <span className="status-chip status-completed">Claimed</span>
                            ) : mission.is_completed ? (
                              <span className="status-chip status-playing">Complete</span>
                            ) : (
                              <span className="status-chip status-waiting">In Progress</span>
                            )}
                          </div>
                        </td>
                        <td>
                          <button
                            type="button"
                            className={`lobby-action-btn ${canClaim ? "" : "disabled"}`}
                            disabled={!canClaim || busy}
                            onClick={() => claimMission(mission.progress_id)}
                          >
                            {mission.is_claimed ? "Claimed" : "Claim"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component profile-section section-engagement-promos">
          <h2 className="component-title">Promo Codes</h2>
          <div className="engagement-promo-row">
            <input
              className="engagement-promo-input"
              type="text"
              value={promoCodeInput}
              maxLength={40}
              onChange={(event) => setPromoCodeInput(event.target.value.toUpperCase())}
              placeholder="Enter promo code"
            />
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => redeemPromo()}>
              Redeem
            </button>
          </div>
          <div className="profile-table-wrap">
            {(promoData.promo_codes || []).length === 0 && <div className="subtitle">No promo campaigns found.</div>}
            {(promoData.promo_codes || []).length > 0 && (
              <table className="profile-table" aria-label="Promo codes table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Tier</th>
                    <th>Reward</th>
                    <th>Window</th>
                    <th>Usage</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {(promoData.promo_codes || []).map((promo) => {
                    const canRedeem = promo.is_live && promo.user_redemptions < promo.per_user_limit;
                    const usageLabel = `${promo.user_redemptions}/${promo.per_user_limit}`;
                    return (
                      <tr key={promo.id}>
                        <td><strong>{promo.code}</strong></td>
                        <td>
                          <span className={`engagement-tier-chip tier-${promo.tier}`}>{formatTitle(promo.tier)}</span>
                        </td>
                        <td>
                          {formatBirr(promo.reward_amount)}
                          <span className={`engagement-balance-chip balance-${promo.reward_balance}`}>
                            {formatTitle(promo.reward_balance)}
                          </span>
                        </td>
                        <td>{formatDate(promo.starts_at)} - {formatDate(promo.ends_at)}</td>
                        <td>{usageLabel}</td>
                        <td>
                          <button
                            type="button"
                            className={`lobby-action-btn ${canRedeem ? "" : "disabled"}`}
                            disabled={!canRedeem || busy}
                            onClick={() => redeemPromo(promo.code)}
                          >
                            {canRedeem ? "Redeem" : "Unavailable"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="component profile-section section-engagement-events">
          <h2 className="component-title">Live Events</h2>
          <div className="engagement-event-grid">
            <div className="engagement-event-col">
              <h3>Active Events</h3>
              {(eventData.active_events || []).length === 0 && <p className="subtitle">No active events right now.</p>}
              {(eventData.active_events || []).map((event) => (
                <article key={event.id} className={`engagement-event-card live event-${event.event_type}`}>
                  <div className="engagement-event-title">{event.name}</div>
                  <div className="engagement-event-meta">{formatTitle(event.event_type)}</div>
                  <div className="engagement-event-meta">{event.bonus_multiplier}x multiplier</div>
                  <div className="engagement-event-meta">Ends: {formatDate(event.ends_at)}</div>
                </article>
              ))}
            </div>
            <div className="engagement-event-col">
              <h3>Upcoming Events</h3>
              {(eventData.upcoming_events || []).length === 0 && <p className="subtitle">No upcoming events.</p>}
              {(eventData.upcoming_events || []).map((event) => (
                <article key={event.id} className={`engagement-event-card event-${event.event_type}`}>
                  <div className="engagement-event-title">{event.name}</div>
                  <div className="engagement-event-meta">{formatTitle(event.event_type)}</div>
                  <div className="engagement-event-meta">{event.bonus_multiplier}x multiplier</div>
                  <div className="engagement-event-meta">Starts: {formatDate(event.starts_at)}</div>
                </article>
              ))}
            </div>
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
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/wallet/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="wallet" /></span>
            <span className="bottom-nav-label">Wallet</span>
          </button>
          <button type="button" className="bottom-nav-item active">
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="engagement" /></span>
            <span className="bottom-nav-label">Engage</span>
          </button>
        </nav>
      </div>
    </div>
  );
}
