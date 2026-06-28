import { useEffect, useState } from "react";
import { api } from "../api";
import type { DeriveContext, DeriveResult, ScoringProfile } from "../api";
import { useLanguage, weaponTypeLabel } from "../i18n";
import { useAuth } from "../auth";
import { useWishlist } from "../store";

const STAT_KEYS = ["handling", "range", "stability", "reload", "aim_assist", "impact", "recoil", "zoom"];
const DEFAULT_SCOPE_BLEND = { weapon: 0.6, frame: 0.25, type: 0.15 };
const DEFAULT_COLUMN_WEIGHTS = { trait: 1.0, barrel: 0.35, magazine: 0.35, origin: 0.2, intrinsic: 0.0 };

function blankProfile(): ScoringProfile {
  return {
    id: null,
    name: "New scoring profile",
    description: "",
    tags: [],
    stat_weights: {},
    perk_weights: {},
    context_weights: {},
    synergy_bonuses: [],
    context_synergies: {},
    use_wishlist_weights: true,
    blend: { stat: 1, perk: 1, synergy: 1 },
    scope_blend: { ...DEFAULT_SCOPE_BLEND },
    column_weights: { ...DEFAULT_COLUMN_WEIGHTS },
    thresholds: { god: 75, viable: 40 },
  };
}

export function ScoringProfileEditor() {
  const { t } = useLanguage();
  const { loggedIn, login } = useAuth();
  const {
    activeProfile, setActiveProfile, rolls,
    profiles, refreshProfiles, upsertProfile, selectedIds, setSelection,
  } = useWishlist();
  const [draft, setDraft] = useState<ScoringProfile>(activeProfile ?? blankProfile());
  const [status, setStatus] = useState("");
  const [contexts, setContexts] = useState<DeriveContext[]>([]);

  function contextLabel(context: DeriveContext): string {
    if (context.kind === "type") {
      const subtype = Number(context.scope.split(":")[1]);
      return weaponTypeLabel(subtype, t, context.label);
    }
    return context.label;
  }

  function applyDerived(res: DeriveResult) {
    const scopeCount = Object.keys(res.context_weights).length;
    if (!scopeCount) {
      setStatus(`${t.scoring.noContext} (${t.wishlist.rolls} ${res.rolls_parsed}).`);
      return;
    }
    setDraft((current) => ({
      ...current,
      context_weights: res.context_weights,
      context_synergies: res.context_synergies,
    }));
    setContexts(res.contexts);
    const combos = res.contexts.reduce((n, c) => n + c.combos.length, 0);
    setStatus(`${t.scoring.learned} - ${scopeCount} ${t.scoring.contextCount}, ${combos} ${t.scoring.combo.toLowerCase()}s (${res.rolls_parsed} ${t.wishlist.rolls}).`);
  }

  async function useCurrentWishlist() {
    if (!rolls.length) {
      setStatus(t.scoring.noWishlist);
      return;
    }
    applyDerived(await api.deriveWeights({ rolls: rolls.map((r) => r.input) }));
  }

  function uploadWishlist(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    file.text().then(async (text) => applyDerived(await api.deriveWeights({ text })));
    e.target.value = "";
  }

  function clearContexts() {
    setDraft((current) => ({ ...current, context_weights: {}, context_synergies: {} }));
    setContexts([]);
  }

  function setStat(key: string, value: number) {
    setDraft((current) => {
      const statWeights = { ...current.stat_weights };
      if (value === 0) delete statWeights[key];
      else statWeights[key] = value;
      return { ...current, stat_weights: statWeights };
    });
  }

  async function save() {
    if (!loggedIn) { setStatus(t.app.loginHint); return; }
    try {
      const saved = await upsertProfile(draft);   // 롤 보존하며 저장
      if (saved) {
        setDraft(saved);
        setActiveProfile(saved);
        setStatus(`${t.scoring.saved}: ${saved.name}`);
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function del(id?: string | null) {
    if (!id) return;
    await api.deleteProfile(id);
    if (draft.id === id) setDraft(blankProfile());
    if (selectedIds.includes(id)) setSelection(selectedIds.filter((x) => x !== id));
    await refreshProfiles();
  }

  // 체크박스: 내 리스트에 합칠 프로필 토글.
  function toggleSelected(id?: string | null) {
    if (!id) return;
    const next = selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id];
    setSelection(next);
  }
  // 기준(primary) 지정 — 선택에 없으면 추가하고 가중치/편집 대상으로.
  function makePrimary(profile: ScoringProfile) {
    setDraft(profile);
    const ids = profile.id && !selectedIds.includes(profile.id) ? [...selectedIds, profile.id] : selectedIds;
    setSelection(ids, profile.id ?? null);
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(draft.name || "profile").replace(/[^0-9A-Za-z가-힣_-]+/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function importJson(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    file.text().then((content) => {
      try {
        const profile = JSON.parse(content) as ScoringProfile;
        profile.id = null;
        setDraft({ ...blankProfile(), ...profile, id: null });
        setStatus(`${t.scoring.imported}: ${profile.name}`);
      } catch {
        setStatus(t.scoring.jsonParseFailed);
      }
    });
  }

  return (
    <div className="layout">
      <div>
        <div className="panel">
          <div className="panel-title">{t.scoring.profileEditor}</div>
          {!loggedIn && (
            <div className="login-gate">
              <span>{t.app.loginHint}</span>
              <button className="btn primary sm" onClick={login}>{t.vault.login}</button>
            </div>
          )}
          <input
            className="text-input"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder={t.scoring.profileName}
          />

          <div className="panel-title" style={{ marginTop: 16 }}>{t.scoring.statWeights}</div>
          {STAT_KEYS.map((key) => (
            <div className="weight-row" key={key}>
              <span className="weight-name">{t.stats[key as keyof typeof t.stats] || key}</span>
              <input
                type="range" min={0} max={3} step={0.5}
                value={draft.stat_weights[key] ?? 0}
                onChange={(e) => setStat(key, Number(e.target.value))}
              />
              <span className="weight-val">{(draft.stat_weights[key] ?? 0).toFixed(1)}</span>
            </div>
          ))}

          <div className="panel-title" style={{ marginTop: 16 }}>{t.scoring.learnTitle}</div>
          <div className="hint" style={{ marginBottom: 8 }}>{t.scoring.learnHint}</div>
          <div className="controls-row" style={{ flexWrap: "wrap" }}>
            <button className="btn ghost" onClick={useCurrentWishlist}>
              {t.scoring.useCurrentWishlist} ({rolls.length} {t.wishlist.rolls})
            </button>
            <label className="btn ghost" style={{ cursor: "pointer" }}>
              {t.scoring.uploadWishlist}
              <input type="file" accept=".txt,text/plain" style={{ display: "none" }} onChange={uploadWishlist} />
            </label>
            {Object.keys(draft.context_weights || {}).length > 0 && (
              <button className="btn ghost" onClick={clearContexts}>{t.scoring.clearLearning}</button>
            )}
          </div>

          {contexts.length > 0 ? (
            <div className="ctx-list">
              {contexts.map((context) => (
                <div className="ctx-group" key={context.scope}>
                  <div className="ctx-head">
                    <span className="ctx-kind">{t.scoring.kind[context.kind as keyof typeof t.scoring.kind] || context.kind}</span>
                    <span className="ctx-label">{contextLabel(context)}</span>
                  </div>
                  <div className="ctx-perks">
                    {context.weights.slice(0, 6).map((weight) => (
                      <span key={weight.plug_hash} className={`ctx-pill ${weight.weight >= 0 ? "up" : "down"}`}>
                        {weight.name || weight.plug_hash} {weight.weight > 0 ? "+" : ""}{weight.weight}
                      </span>
                    ))}
                  </div>
                  {context.combos.length > 0 && (
                    <div className="ctx-combos">
                      {t.scoring.combo}: {context.combos.map((combo, index) => (
                        <span key={index} className="ctx-combo">{combo.perks.map((perk) => perk.name || perk.plug_hash).join("+")}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            Object.keys(draft.context_weights || {}).length > 0 && (
              <div className="hint" style={{ marginTop: 8 }}>
                {Object.keys(draft.context_weights || {}).length} {t.scoring.registeredContexts}
              </div>
            )
          )}

          <div className="panel-title" style={{ marginTop: 16 }}>{t.scoring.scoreWeights}</div>
          <div className="hint" style={{ marginBottom: 8 }}>{t.scoring.scoreHint}</div>
          <div className="blend-info">
            <span className="blend-label">{t.scoring.scope}</span>
            {Object.entries(draft.scope_blend ?? DEFAULT_SCOPE_BLEND).map(([key, value]) => (
              <span key={key} className="blend-pill">
                {key === "weapon" ? t.scoring.sameWeapon : key === "frame" ? t.scoring.sameFrame : key === "type" ? t.scoring.sameType : key} {Math.round(value * 100)}%
              </span>
            ))}
          </div>
          <div className="blend-info">
            <span className="blend-label">{t.scoring.columnWeight}</span>
            {Object.entries(draft.column_weights ?? DEFAULT_COLUMN_WEIGHTS)
              .filter(([, value]) => value > 0)
              .map(([key, value]) => (
                <span key={key} className="blend-pill">{t.scoring.columns[key as keyof typeof t.scoring.columns] || key} ×{value}</span>
              ))}
          </div>

          <div className="controls-row" style={{ marginTop: 14 }}>
            <label className="toggle" style={{ cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={draft.use_wishlist_weights}
                onChange={(e) => setDraft({ ...draft, use_wishlist_weights: e.target.checked })}
              />
              {t.scoring.autoWishlistWeights}
            </label>
          </div>

          <div className="controls-row">
            <label className="filter-stat">{t.scoring.godThreshold}
              <input type="number" className="text-input"
                     value={draft.thresholds.god}
                     onChange={(e) => setDraft({ ...draft, thresholds: { ...draft.thresholds, god: Number(e.target.value) } })} />
            </label>
            <label className="filter-stat">{t.scoring.viableThreshold}
              <input type="number" className="text-input"
                     value={draft.thresholds.viable}
                     onChange={(e) => setDraft({ ...draft, thresholds: { ...draft.thresholds, viable: Number(e.target.value) } })} />
            </label>
          </div>

          <div className="controls-row" style={{ marginTop: 12, gap: 8, flexWrap: "wrap" }}>
            <button className="btn primary" onClick={save}>{t.scoring.saveActivate}</button>
            <button className="btn ghost" onClick={() => setDraft(blankProfile())}>{t.scoring.createNew}</button>
            <button className="btn ghost" onClick={exportJson}>{t.scoring.exportJson}</button>
            <label className="btn ghost" style={{ cursor: "pointer" }}>
              {t.scoring.importJson}
              <input type="file" accept="application/json" style={{ display: "none" }} onChange={importJson} />
            </label>
          </div>
          {status && <div className="hint" style={{ marginTop: 8, color: "var(--success)" }}>{status}</div>}
          <div className="hint" style={{ marginTop: 8 }}>{t.scoring.jsonHint}</div>
        </div>
      </div>

      <div>
        <div className="panel chamfer">
          <div className="panel-title">{t.scoring.savedProfiles}</div>
          {activeProfile && (
            <div className="hint" style={{ marginBottom: 8 }}>
              {t.scoring.active}: <strong style={{ color: "var(--primary-hover)" }}>{activeProfile.name}</strong>
            </div>
          )}
          {profiles.length === 0 && <div className="empty">{t.scoring.noProfiles}</div>}
          {profiles.map((profile) => {
            const isSel = !!profile.id && selectedIds.includes(profile.id);
            const isPrimary = activeProfile?.id === profile.id;
            return (
              <div key={profile.id} className={`roll-item ${isPrimary ? "wild" : ""}`}>
                <label className="prof-check" title={t.scoring.includeInList}>
                  <input type="checkbox" checked={isSel} onChange={() => toggleSelected(profile.id)} />
                </label>
                <div className="r-main">
                  <div className="r-name">{profile.name}{isPrimary ? " ★" : ""}</div>
                  <div className="r-perks">
                    {profile.rolls?.length ?? 0} {t.wishlist.rolls}
                    {` · ${Object.keys(profile.stat_weights || {}).length} ${t.scoring.statsCount}`}
                    {profile.use_wishlist_weights ? ` · ${t.scoring.wishlistWeighted}` : ""}
                  </div>
                </div>
                <button className="btn ghost" style={{ padding: "4px 8px", fontSize: 12 }}
                        onClick={() => makePrimary(profile)}>
                  {isPrimary ? t.scoring.active : t.scoring.activate}
                </button>
                <button className="icon-btn" title={t.scoring.delete} onClick={() => del(profile.id)}>✕</button>
              </div>
            );
          })}
          <button className="btn ghost" style={{ marginTop: 8 }} onClick={() => setActiveProfile(null)}>
            {t.scoring.disableScoring}
          </button>
        </div>
      </div>
    </div>
  );
}