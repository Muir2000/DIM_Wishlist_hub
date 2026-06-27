import { useEffect, useState } from "react";
import { api, inventoryApi, CLASS_COLOR, ELEM_VAR, RARITY_VAR } from "../api";
import type { CleanupItem, RollInput, ScoreResult, WeaponDetail, WeaponSummary } from "../api";
import { damageLabel, displayName, formatTemplate, seasonName, slotLabel, tierLabel, useLanguage, weaponTypeLabel } from "../i18n";
import { PerkGrid } from "./PerkGrid";
import { StatsPanel } from "./StatsPanel";
import { WishlistPanel } from "./WishlistPanel";
import { useAuth } from "../auth";
import { useWishlist } from "../store";

const TAGS = ["PvE", "PvP", "GM", "레이드"];

export function Builder({ picked }: { picked: WeaponSummary | null }) {
  const { language, t } = useLanguage();
  const { loggedIn } = useAuth();
  const { addRoll, activeProfile, rolls } = useWishlist();
  const [weapon, setWeapon] = useState<WeaponDetail | null>(null);
  const [selection, setSelection] = useState<Record<number, number[]>>({});
  const [trash, setTrash] = useState(false);
  const [wildcard, setWildcard] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [score, setScore] = useState<ScoreResult | null>(null);
  const [perkW, setPerkW] = useState<{
    weights: Record<number, number>;
    scale: number;
    signal: boolean;
    maxPossible: number;
    coverage: number;
    columnWeights: Record<string, number>;
    kinds: Record<number, string>;
  } | null>(null);
  const [owned, setOwned] = useState<CleanupItem[]>([]);   // 로그인 유저가 보유한 이 무기 인스턴스

  const selectedPerks = Object.values(selection).flat();
  useEffect(() => {
    if (!weapon || !activeProfile) {
      setScore(null);
      return;
    }
    const timeout = window.setTimeout(() => {
      api
        .score({
          weapon_hash: weapon.item_hash,
          perks: selectedPerks,
          profile: activeProfile,
          wishlist_rolls: rolls.map((r) => r.input),
        })
        .then(setScore)
        .catch(() => setScore(null));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [weapon, activeProfile, JSON.stringify(selectedPerks), rolls]);

  useEffect(() => {
    if (!weapon || !activeProfile) {
      setPerkW(null);
      return;
    }
    let cancelled = false;
    api
      .perkWeights({
        weapon_hash: weapon.item_hash,
        profile: activeProfile,
        wishlist_rolls: rolls.map((r) => r.input),
      })
      .then((res) => {
        if (cancelled) return;
        const weights: Record<number, number> = {};
        for (const [k, v] of Object.entries(res.weights)) weights[Number(k)] = v;
        const kinds: Record<number, string> = {};
        for (const [k, v] of Object.entries(res.kinds)) kinds[Number(k)] = v;
        setPerkW({
          weights, scale: res.scale, signal: res.has_signal,
          maxPossible: res.max_possible, coverage: res.coverage,
          columnWeights: res.column_weights, kinds,
        });
      })
      .catch(() => { if (!cancelled) setPerkW(null); });
    return () => { cancelled = true; };
  }, [weapon, activeProfile, rolls]);

  // 로그인 유저가 이 무기를 보유 중이면 인스턴스(퍽롤+점수)를 조회.
  useEffect(() => {
    if (!weapon || !loggedIn) { setOwned([]); return; }
    let cancelled = false;
    inventoryApi
      .weaponRolls(weapon.item_hash, activeProfile, rolls.map((r) => r.input))
      .then((list) => { if (!cancelled) setOwned(list); })
      .catch(() => { if (!cancelled) setOwned([]); });
    return () => { cancelled = true; };
  }, [weapon, loggedIn, activeProfile, rolls]);

  function resetBuilder() {
    setSelection({});
    setTrash(false);
    setWildcard(false);
    setTags([]);
    setNotes("");
  }

  useEffect(() => {
    if (!picked) { setWeapon(null); return; }
    resetBuilder();
    let cancelled = false;
    api.weapon(picked.item_hash)
      .then((detail) => { if (!cancelled) setWeapon(detail); })
      .catch(() => { if (!cancelled) setWeapon(null); });
    return () => { cancelled = true; };
  }, [picked?.item_hash]);

  function toggle(col: number, hash: number) {
    setSelection((prev) => {
      const cur = prev[col] ?? [];
      const next = cur.includes(hash) ? cur.filter((h) => h !== hash) : [...cur, hash];
      const copy = { ...prev };
      if (next.length) copy[col] = next;
      else delete copy[col];
      return copy;
    });
  }

  function toggleTag(tag: string) {
    setTags((prev) => (prev.includes(tag) ? prev.filter((x) => x !== tag) : [...prev, tag]));
  }

  const colCount = Object.keys(selection).length;
  const comboCount = colCount
    ? Object.values(selection).reduce((acc, arr) => acc * arr.length, 1)
    : 0;
  const canAdd = !!weapon && (colCount > 0 || trash);

  async function add() {
    if (!weapon) return;
    setBusy(true);
    try {
      const columns: Record<string, number[]> = {};
      Object.entries(selection).forEach(([k, v]) => {
        columns[k] = v;
      });
      const weaponName = displayName(weapon, language);
      const input: RollInput = {
        weapon_hash: weapon.item_hash,
        columns,
        wildcard,
        trash,
        notes,
        tags,
        comment: weaponName,
      };
      const res = await api.compile(input);
      const labelOf = (hash: number) => {
        for (const col of weapon.columns) {
          const perk = col.perks.find((pp) => pp.plug_hash === hash);
          if (perk) return displayName(perk, language);
        }
        return String(hash);
      };
      const perkLabels = Object.values(selection).flat().map(labelOf);
      addRoll({
        input, weaponName, perkLabels, lines: res.lines,
        typeLabel: weaponTypeLabel(weapon.weapon_subtype, t, weapon.type_label),
        damageType: weapon.default_damage_type,
        tier: weapon.tier,
      });
      resetBuilder();
    } finally {
      setBusy(false);
    }
  }

  const elemVar = weapon?.default_damage_type ? ELEM_VAR[weapon.default_damage_type] : undefined;
  const rarityVar = weapon?.tier ? RARITY_VAR[weapon.tier] : undefined;
  const cls = score?.classification ?? null;
  const cov = score?.coverage ?? (perkW?.signal ? perkW.coverage : null);
  const weaponName = weapon ? displayName(weapon, language) : "";

  return (
    <div className="builder-main">
      <div className="builder-col">
        {!weapon ? (
          <div className="panel">
            <div className="empty">{t.builder.empty}</div>
          </div>
        ) : (
          <>
            <div
              className="weapon-header"
              style={
                {
                  ["--elem-color" as any]: elemVar ? `var(${elemVar})` : undefined,
                  ["--rarity-wash" as any]: rarityVar ? `var(${rarityVar})` : undefined,
                } as React.CSSProperties
              }
            >
              <span className="elem-bar" />
              {weapon.icon ? <img className="w-icon" src={weapon.icon} alt="" /> : <div className="w-icon" />}
              <div>
                <div className="w-name">{weaponName}</div>
                <div className="w-sub">
                  {weaponTypeLabel(weapon.weapon_subtype, t, weapon.type_label)}
                  {weapon.default_damage_type ? <> · <span className="elem-name">{damageLabel(weapon.default_damage_type, t, weapon.damage_label)}</span></> : ""}
                  {weapon.slot ? ` · ${slotLabel(weapon.slot, t, weapon.slot)}` : ""}
                  {weapon.tier ? ` · ${tierLabel(weapon.tier, t, weapon.tier_label)}` : ""}
                  {weapon.season_number ? (
                    <> · <span className="w-season" title={`${t.labels.season} ${weapon.season_number}: ${seasonName(weapon, language)}`}>
                      {weapon.watermark && <img className="w-season-wm" src={weapon.watermark} alt="" />}
                      S{weapon.season_number}{seasonName(weapon, language) ? ` · ${seasonName(weapon, language)}` : ""}
                    </span></>
                  ) : null}
                </div>
                {weapon.season_count && weapon.season_count > 1 && (
                  <div className="variant-note" title={t.builder.seasonVariantTitle}>
                    {t.builder.seasonVariantPrefix} <b>{weapon.season_count}</b> {t.builder.seasonVariantSuffix}
                    {weapon.has_holofoil && <> {t.labels.holofoil} ✦ ({t.labels.samePerkRoll}).</>}
                    {" "}{t.builder.currentSeasonPool}
                  </div>
                )}
              </div>
            </div>

            <div className="panel">
              <div className="panel-head">
                <span className="panel-title" style={{ margin: 0 }}>{t.builder.perkSelection}</span>
                <span className="panel-actions">{t.builder.multiPerkHint}</span>
              </div>

              {weapon.stats && Object.keys(weapon.stats).length > 0 && (
                <StatsPanel
                  stats={weapon.stats}
                  deltas={(() => {
                    const d: Record<string, number> = {};
                    for (const hashes of Object.values(selection)) {
                      for (const hash of hashes) {
                        for (const col of weapon.columns) {
                          const perk = col.perks.find((pp) => pp.plug_hash === hash);
                          if (perk?.stats) {
                            for (const [k, v] of Object.entries(perk.stats)) {
                              d[k] = (d[k] ?? 0) + v;
                            }
                          }
                        }
                      }
                    }
                    return d;
                  })()}
                />
              )}

              <div style={{ marginTop: 16 }}>
                <PerkGrid
                  weapon={weapon}
                  selection={selection}
                  onToggle={toggle}
                  weights={perkW?.signal ? perkW.weights : null}
                  scale={perkW?.scale ?? 50}
                  maxPossible={perkW?.maxPossible}
                  columnWeights={perkW?.columnWeights}
                  kinds={perkW?.kinds}
                />
              </div>
            </div>

            {loggedIn && owned.length > 0 && (
              <div className="panel">
                <div className="panel-title" style={{ marginTop: 0 }}>
                  {t.builder.ownedRolls} ({owned.length})
                </div>
                {owned.map((it) => {
                  const ocls = it.classification;
                  const color = ocls ? CLASS_COLOR[ocls] : "var(--border-strong)";
                  return (
                    <div key={it.item_instance_id} className="owned-roll">
                      <div className="owned-perks">
                        {it.perks.length === 0 && <span className="hint">{t.vault.noPerks}</span>}
                        {it.perks.map((p) => {
                          const shape = p.column_kind === "barrel" || p.column_kind === "magazine" ? "square" : "circle";
                          const label = displayName(p, language);
                          return (
                            <div key={p.plug_hash} className={`perk-icon ${shape}`} title={label}>
                              {p.icon ? <img src={p.icon} alt="" loading="lazy" /> : (label?.[0] ?? "?")}
                            </div>
                          );
                        })}
                      </div>
                      {it.score != null && (
                        <div
                          className="score-pill"
                          style={{ color, border: `1px solid ${color}`, fontSize: 13, padding: "4px 10px" }}
                        >
                          {it.score}{ocls ? ` · ${t.scoring.classLabel[ocls as keyof typeof t.scoring.classLabel]}` : ""}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      <aside className="roll-side">
        {weapon && (
          <div className="panel roll-panel">
            <div className="panel-title" style={{ marginTop: 0 }}>{t.builder.currentRoll}</div>

            {!activeProfile ? (
              <div className="score-hint">{t.builder.scoreNoProfile}</div>
            ) : score && score.score != null && cls ? (
              <div className="roll-score" style={{ ["--score-color" as any]: CLASS_COLOR[cls] }}>
                <div className="rs-top">
                  <span className="rs-num">{score.score}</span>
                  <span className="rs-max">/100</span>
                  <span className="rs-cls">{t.scoring.classLabel[cls as keyof typeof t.scoring.classLabel]}</span>
                </div>
                <div className="rs-bd">
                  {score.breakdown.perk != null && `${t.labels.perk} ${score.breakdown.perk}`}
                  {score.breakdown.synergy != null && ` · ${t.labels.synergy} +${score.breakdown.synergy}`}
                </div>
              </div>
            ) : (
              <div className="score-hint">{t.builder.scoreNoSignal}</div>
            )}

            {cov != null && cov < 1 && (
              <div className="coverage-note" title={t.builder.coverageTitle}>
                ⓘ {t.builder.coverageText} ({Math.round(cov * 100)}% max)
              </div>
            )}

            <div className="controls-row" style={{ marginTop: 14 }}>
              <button
                className={`toggle trash ${trash ? "on" : ""}`}
                onClick={() => {
                  setTrash((value) => !value);
                  if (!trash) setWildcard(false);
                }}
              >
                👎 {t.labels.trashRoll}
              </button>
              <button
                className={`toggle wild ${wildcard ? "on" : ""}`}
                onClick={() => {
                  setWildcard((value) => !value);
                  if (!wildcard) setTrash(false);
                }}
              >
                ✷ {t.labels.wildcard}
              </button>
            </div>
            <div className="tag-chips" style={{ marginBottom: 12 }}>
              {TAGS.map((tag) => (
                <button
                  key={tag}
                  className={`chip ${tags.includes(tag) ? "on" : ""}`}
                  onClick={() => toggleTag(tag)}
                >
                  {tag}
                </button>
              ))}
            </div>

            <textarea
              className="text-input"
              rows={2}
              placeholder={t.builder.notesPlaceholder}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />

            <div className="hint" style={{ marginTop: 10 }}>
              {wildcard ? `${t.builder.wildcardHint} ` : trash ? `${t.builder.trashHint} ` : ""}
              {colCount > 0 ? `· ${formatTemplate(t.builder.lineExpansion, { count: comboCount })}` : `· ${t.builder.noPerks}`}
            </div>
            <button
              className="btn primary"
              style={{ width: "100%", marginTop: 10 }}
              disabled={!canAdd || busy}
              onClick={add}
            >
              + {t.builder.addToWishlist}
            </button>
          </div>
        )}

        <WishlistPanel />
      </aside>
    </div>
  );
}