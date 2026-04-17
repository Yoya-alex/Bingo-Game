import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchJson, postJson } from "../api/client.js";
import { withAuthPath } from "../utils/auth.js";
import NotificationComponent from "../components/NotificationComponent.jsx";
import BottomNavIcon from "../components/BottomNavIcon.jsx";
import { useI18n } from "../i18n/LanguageContext.jsx";

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

function promoStatusMeta(promo, t) {
  const status = String(promo?.claim_status || "");
  if (status.includes("pending")) {
    return { label: t("engagement.pendingVerification"), chip: "status-waiting" };
  }
  if (status.includes("approved")) {
    return { label: t("engagement.approved"), chip: "status-completed" };
  }
  if (status.includes("rejected")) {
    return { label: t("engagement.rejected"), chip: "status-rejected" };
  }
  if (promo?.is_live) {
    return { label: t("engagement.live"), chip: "status-playing" };
  }
  return { label: t("engagement.unavailable"), chip: "status-finished" };
}

export default function EngagementPage() {
  const { telegramId } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();

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

  function hidePromoOverlay() {
    setPromoOverlay(EMPTY_PROMO_OVERLAY);
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
      notify("error", t("engagement.enterPromoFirst"));
      return;
    }

    setBusy(true);
    try {
      const payload = await postJson("/game/api/redeem-promo-code/", {
        telegram_id: Number(telegramId),
        code: promoCode,
      });
      if (payload.requires_verification) {
        showPromoOverlay("success", payload.message || t("engagement.promoSubmitted"));
      } else {
        showPromoOverlay("success", t("engagement.promoRedeemed", { code: payload.code, amount: formatBirr(payload.credited_amount) }));
      }
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
      notify("success", t("engagement.missionClaimed", { amount: formatBirr(payload.reward_amount) }));
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
          <div className="loading-state" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <div className="subtitle">{t("engagement.loading")}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell profile-shell">
      <div className="app-card profile-card engagement-card">
        <header className="component profile-header engagement-header">
          <h1 className="title profile-title">{t("engagement.title")}</h1>
          <p className="subtitle profile-subtitle">
            {t("engagement.subtitle")}
          </p>
        </header>

        <NotificationComponent notification={notification} />

        {promoOverlay.show && (
          <div className="engagement-overlay" role="status" aria-live="polite" onClick={hidePromoOverlay}>
            <div className={`engagement-overlay-card ${promoOverlay.type}`} onClick={(event) => event.stopPropagation()}>
              <h3>{promoOverlay.type === "success" ? t("engagement.promoApplied") : t("engagement.promoUnavailable")}</h3>
              <p>{promoOverlay.message}</p>
            </div>
          </div>
        )}

        <section className="component profile-section section-engagement-streak">
          <h2 className="component-title">{t("engagement.dailyStreak")}</h2>
          <div className="profile-grid profile-grid-4">
            <div className="profile-metric"><span>{t("engagement.currentStreak")}</span><strong>{missionData.streak?.current_streak || 0}</strong></div>
            <div className="profile-metric"><span>{t("engagement.bestStreak")}</span><strong>{missionData.streak?.best_streak || 0}</strong></div>
            <div className="profile-metric"><span>{t("engagement.streakProtect")}</span><strong>{missionData.streak?.streak_protect_tokens || 0}</strong></div>
            <div className="profile-metric"><span>{t("engagement.lastActive")}</span><strong>{missionData.streak?.last_active_date || "-"}</strong></div>
          </div>
        </section>

        <section className="component profile-section section-engagement-missions">
          <h2 className="component-title">{t("engagement.missions")}</h2>
          {claimableMissions.length > 0 && (
            <div className="engagement-claim-banner">
              {t("engagement.claimReady", { count: claimableMissions.length })}
            </div>
          )}
          <div className="profile-table-wrap">
            {(missionData.missions || []).length === 0 && <div className="subtitle">{t("engagement.noActiveMissions")}</div>}
            {(missionData.missions || []).length > 0 && (
              <table className="profile-table" aria-label={t("engagement.missionsAria")}>
                <thead>
                  <tr>
                    <th>{t("engagement.mission")}</th>
                    <th>{t("engagement.periodProgress")}</th>
                    <th>{t("engagement.rewardStatus")}</th>
                    <th>{t("home.action")}</th>
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
                              <span className="status-chip status-completed">{t("engagement.claimed")}</span>
                            ) : mission.is_completed ? (
                              <span className="status-chip status-playing">{t("engagement.complete")}</span>
                            ) : (
                              <span className="status-chip status-waiting">{t("engagement.inProgress")}</span>
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
                            {mission.is_claimed ? t("engagement.claimed") : t("engagement.claim")}
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
          <h2 className="component-title">{t("engagement.promoCodes")}</h2>
          <div className="engagement-promo-row">
            <input
              className="engagement-promo-input"
              type="text"
              value={promoCodeInput}
              maxLength={40}
              onChange={(event) => setPromoCodeInput(event.target.value.toUpperCase())}
              placeholder={t("engagement.enterPromoCode")}
            />
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => redeemPromo()}>
              {busy ? <span className="spinner-inline"><span className="spinner sm" aria-hidden="true" /></span> : null}
              {t("engagement.redeem")}
            </button>
          </div>
          <div className="profile-table-wrap">
            {(promoData.promo_codes || []).length === 0 && <div className="subtitle">{t("engagement.noPromoCampaigns")}</div>}
            {(promoData.promo_codes || []).length > 0 && (
              <table className="profile-table" aria-label={t("engagement.promoCodesAria")}>
                <thead>
                  <tr>
                    <th>{t("profile.code")}</th>
                    <th>{t("engagement.tier")}</th>
                    <th>{t("engagement.reward")}</th>
                    <th>{t("wallet.status")}</th>
                    <th>{t("engagement.window")}</th>
                    <th>{t("engagement.usage")}</th>
                    <th>{t("home.action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {(promoData.promo_codes || []).map((promo) => {
                    const blockedByClaim = ["pending_verification", "approved"].includes(String(promo.claim_status || ""));
                    const canRedeem = promo.is_live && promo.user_redemptions < promo.per_user_limit && !blockedByClaim;
                    const usageLabel = `${promo.user_redemptions}/${promo.per_user_limit}`;
                    const statusMeta = promoStatusMeta(promo, t);
                    return (
                      <tr key={`${promo.id}-${promo.claim_submitted_at || "none"}`}>
                        <td>
                          <strong>{promo.code}</strong>
                          {promo.is_hidden_claim ? <div className="wallet-note-inline">{t("engagement.hiddenPromoClaim")}</div> : null}
                        </td>
                        <td>
                          <span className={`engagement-tier-chip tier-${promo.tier}`}>{formatTitle(promo.tier)}</span>
                        </td>
                        <td>
                          {formatBirr(promo.reward_amount)}
                          <span className={`engagement-balance-chip balance-${promo.reward_balance}`}>
                            {formatTitle(promo.reward_balance)}
                          </span>
                        </td>
                        <td>
                          <span className={`status-chip ${statusMeta.chip}`}>{statusMeta.label}</span>
                          {promo.claim_review_reason ? <div className="wallet-note-inline">{promo.claim_review_reason}</div> : null}
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
                            {promo.claim_status === "pending_verification" ? t("engagement.pending") : canRedeem ? t("engagement.redeem") : t("engagement.unavailable")}
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
          <h2 className="component-title">{t("engagement.liveEvents")}</h2>
          <div className="engagement-event-grid">
            <div className="engagement-event-col">
              <h3>{t("engagement.activeEvents")}</h3>
              {(eventData.active_events || []).length === 0 && <p className="subtitle">{t("engagement.noActiveEvents")}</p>}
              {(eventData.active_events || []).map((event) => (
                <article key={event.id} className={`engagement-event-card live event-${event.event_type}`}>
                  <div className="engagement-event-title">{event.name}</div>
                  <div className="engagement-event-meta">{formatTitle(event.event_type)}</div>
                  <div className="engagement-event-meta">{t("engagement.multiplier", { count: event.bonus_multiplier })}</div>
                  <div className="engagement-event-meta">{t("engagement.ends")}: {formatDate(event.ends_at)}</div>
                </article>
              ))}
            </div>
            <div className="engagement-event-col">
              <h3>{t("engagement.upcomingEvents")}</h3>
              {(eventData.upcoming_events || []).length === 0 && <p className="subtitle">{t("engagement.noUpcomingEvents")}</p>}
              {(eventData.upcoming_events || []).map((event) => (
                <article key={event.id} className={`engagement-event-card event-${event.event_type}`}>
                  <div className="engagement-event-title">{event.name}</div>
                  <div className="engagement-event-meta">{formatTitle(event.event_type)}</div>
                  <div className="engagement-event-meta">{t("engagement.multiplier", { count: event.bonus_multiplier })}</div>
                  <div className="engagement-event-meta">{t("engagement.starts")}: {formatDate(event.starts_at)}</div>
                </article>
              ))}
            </div>
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
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/trophy/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="trophy" /></span>
            <span className="bottom-nav-label">{t("common.topWinners")}</span>
          </button>
          <button type="button" className="bottom-nav-item" onClick={() => navigate(withAuthPath(`/wallet/${telegramId}`))}>
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="wallet" /></span>
            <span className="bottom-nav-label">{t("common.wallet")}</span>
          </button>
          <button type="button" className="bottom-nav-item active">
            <span className="bottom-nav-icon" aria-hidden="true"><BottomNavIcon name="engagement" /></span>
            <span className="bottom-nav-label">{t("common.engage")}</span>
          </button>
        </nav>
      </div>
    </div>
  );
}
