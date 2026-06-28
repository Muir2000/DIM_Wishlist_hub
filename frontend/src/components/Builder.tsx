import { useEffect, useState } from "react";
import { api, inventoryApi, CLASS_COLOR, ELEM_VAR, RARITY_VAR, perkTier, PERK_TIER_COLOR } from "../api";
import type { CleanupItem, RollInput, ScoreResult, TagScores, WeaponDetail, WeaponSummary } from "../api";
import { damageLabel, displayName, formatTemplate, seasonName, slotLabel, tierLabel, useLanguage, weaponTypeLabel } from "../i18n";
import { PerkGrid } from "./PerkGrid";
import { StatsPanel } from "./StatsPanel";
import { WishlistPanel } from "./WishlistPanel";
import { useAuth } from "../auth";
import { useWishlist } from "../store";

const TAGS = ["PvE", "PvP", "GM", "레이드"];

export function Builder({ picked, pending, clearPending, onLoadRoll }: {
  picked: WeaponSummary | null;
  pending?: { hash: number; columns: Record<string, number[]> } | null;
  clearPending?: () => void;
  onLoadRoll?: (hash: number, columns: Record<string, number[]>, summary?: Partial<WeaponSummary>) => void;
}) {
  const { language, t } = useLanguage();
  const { loggedIn } = useAuth();
  const { addRoll, activeProfile, scoringProfile, rolls } = useWishlist();
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
  const [tagScores, setTagScores] = useState<TagScores | null>(null);  // 종합 + 태그별 점수/추천
  const [copiedVal, setCopiedVal] = useState<string | null>(null);  // 복사 피드백(값별)
  const copyText = (val: string) => {
    navigator.clipboard?.writeText(val);
    setCopiedVal(val);
    window.setTimeout(() => setCopiedVal((c) => (c === val ? null : c)), 1200);
  };

  const selectedPerks = Object.values(selection).flat();
  useEffect(() => {
    if (!weapon || !scoringProfile) {
      setScore(null);
      return;
    }
    const timeout = window.setTimeout(() => {
      api
        .score({
          weapon_hash: weapon.item_hash,
          perks: selectedPerks,
          profile: scoringProfile,
          wishlist_rolls: rolls.map((r) => r.input),
        })
        .then(setScore)
        .catch(() => setScore(null));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [weapon, scoringProfile, JSON.stringify(selectedPerks), rolls]);

  // 종합 + 태그별(PvE/PvP/GM) 점수·추천.
  useEffect(() => {
    if (!weapon || !scoringProfile) { setTagScores(null); return; }
    const timeout = window.setTimeout(() => {
      api.scoreTags({
        weapon_hash: weapon.item_hash,
        perks: selectedPerks,
        profile: scoringProfile,
        wishlist_rolls: rolls.map((r) => r.input),
      }).then(setTagScores).catch(() => setTagScores(null));
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [weapon, scoringProfile, JSON.stringify(selectedPerks), rolls]);

  useEffect(() => {
    if (!weapon || !scoringProfile) {
      setPerkW(null);
      return;
    }
    let cancelled = false;
    api
      .perkWeights({
        weapon_hash: weapon.item_hash,
        profile: scoringProfile,
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
  }, [weapon, scoringProfile, rolls]);

  // 로그인 유저가 이 무기를 보유 중이면 인스턴스(퍽롤+점수)를 조회.
  useEffect(() => {
    if (!weapon || !loggedIn) { setOwned([]); return; }
    let cancelled = false;
    inventoryApi
      .weaponRolls(weapon.item_hash, scoringProfile, rolls.map((r) => r.input))
      .then((list) => { if (!cancelled) setOwned(list); })
      .catch(() => { if (!cancelled) setOwned([]); });
    return () => { cancelled = true; };
  }, [weapon, loggedIn, scoringProfile, rolls]);

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

  // 불러온 롤(pending)을 무기 로드 후 적용(같은 무기 재로드도 처리). columns→selection.
  useEffect(() => {
    if (!pending || !weapon || pending.hash !== weapon.item_hash) return;
    const sel: Record<number, number[]> = {};
    for (const [k, v] of Object.entries(pending.columns)) sel[Number(k)] = v;
    setSelection(sel);
    clearPending?.();
  }, [pending, weapon]);

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

  // 활성 프로필 가중치 기준 열별 최고(양수) 퍽 자동 선택 = 최적 롤.
  function applyMaxRoll() {
    if (!weapon || !perkW) return;
    const sel: Record<number, number[]> = {};
    for (const col of weapon.columns) {
      let bestHash: number | null = null;
      let bestW = 0;
      for (const p of col.perks) {
        const w = perkW.weights[p.plug_hash] ?? 0;
        if (w > bestW) { bestW = w; bestHash = p.plug_hash; }
      }
      if (bestHash != null) sel[col.index] = [bestHash];
    }
    setSelection(sel);
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
                <div className="w-name">
                  {weaponName}
                  {(() => {
                    // 보유 중이면 창고 사본의 instanceId(DIM: id:<…>), 아니면 검색 무기 item_hash.
                    const fromVault = owned.length > 0;
                    const idVal = fromVault ? owned[0].item_instance_id : String(weapon.item_hash);
                    return (
                      <button
                        className="copy-hash"
                        title={fromVault ? t.builder.copyHashVault : t.builder.copyHash}
                        onClick={() => copyText(idVal)}
                      >{copiedVal === idVal ? `✓ ${t.builder.copied}` : (fromVault ? "⧉ ID 🗄" : `⧉ ${idVal}`)}</button>
                    );
                  })()}
                </div>
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
                <span className="panel-actions">
                  {perkW?.signal && (
                    <button className="btn ghost sm best-roll-btn" title={t.builder.bestRollApply}
                            onClick={applyMaxRoll}>★ {t.builder.bestRoll}</button>
                  )}
                  {t.builder.multiPerkHint}
                </span>
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
                <div className="panel-title owned-head" style={{ marginTop: 0 }}>
                  {weapon.icon && <img className="owned-weapon-icon" src={weapon.icon} alt="" />}
                  <span>{weaponName} · {t.builder.ownedRolls} ({owned.length})</span>
                </div>
                {owned.map((it) => {
                  const ocls = it.classification;
                  const color = ocls ? CLASS_COLOR[ocls] : "var(--border-strong)";
                  // 열별 선택 가능 퍽(제작=다중). perk_columns 우선, 없으면 장착 퍽을 열당 하나로.
                  const columns = it.perk_columns && it.perk_columns.length > 0
                    ? it.perk_columns
                    : [...it.perks]
                        .sort((a, b) => (a.column_index ?? 99) - (b.column_index ?? 99))
                        .map((p) => [p]);
                  return (
                    <div key={it.item_instance_id} className="owned-roll">
                      <div className="owned-cols">
                        {columns.length === 0 && <span className="hint">{t.vault.noPerks}</span>}
                        {columns.map((col, ci) => (
                          <div key={ci} className="owned-col">
                            {col.map((p) => {
                              const shape = p.column_kind === "barrel" || p.column_kind === "magazine" ? "square" : "circle";
                              const label = displayName(p, language);
                              const tier = p.points != null && p.points !== 0 ? perkTier(p.points) : null;
                              const tColor = tier ? PERK_TIER_COLOR[tier] : undefined;
                              return (
                                <span
                                  key={p.plug_hash}
                                  className={`owned-perk ${p.equipped ? "on" : ""}`}
                                  title={p.points != null ? `${label} (${p.points > 0 ? "+" : ""}${p.points})` : label}
                                  style={tColor ? { borderColor: tColor } : undefined}
                                >
                                  <span className={`perk-icon ${shape}`}>
                                    {p.icon ? <img src={p.icon} alt="" loading="lazy" /> : (label?.[0] ?? "?")}
                                  </span>
                                  <span className="owned-perk-name">{label}</span>
                                  {p.points != null && p.points !== 0 && (
                                    <span className="owned-perk-pts" style={{ color: tColor }}>
                                      {p.points > 0 ? "+" : ""}{p.points}
                                    </span>
                                  )}
                                </span>
                              );
                            })}
                          </div>
                        ))}
                      </div>
                      {(it.score != null || it.best_score != null) && (
                        <div className="owned-scores" style={{ flexShrink: 0 }}>
                          {it.score != null && (
                            <div className="score-pill" style={{ color, border: `1px solid ${color}`, fontSize: 13, padding: "4px 10px" }}>
                              {it.score}{ocls ? ` · ${t.scoring.classLabel[ocls as keyof typeof t.scoring.classLabel]}` : ""}
                            </div>
                          )}
                          {it.best_score != null && it.best_score !== it.score && (
                            <div className="owned-best" title={t.builder.bestRollHint}>
                              ★ {it.best_score}
                            </div>
                          )}
                        </div>
                      )}
                      <button
                        className="btn ghost sm owned-load"
                        title={t.builder.copyHashVault}
                        onClick={() => copyText(it.item_instance_id)}
                      >{copiedVal === it.item_instance_id ? "✓" : "⧉"}</button>
                      {onLoadRoll && (
                        <button
                          className="btn ghost sm owned-load"
                          title={t.builder.loadRoll}
                          onClick={() => {
                            // 다중 퍽 전부: 열별 선택 가능 퍽(perk_columns) → 열당 OR.
                            // 열 단위로 키 부여(열의 column_index 우선, 없으면 배열 순서) → 시즌 변형으로
                            // column_index 가 null 인 퍽도 누락 없이 로드.
                            // 기본형 해시(base_hash)로 로드 — 빌더 그리드는 기본형을 쓰므로 강화 퍽도 매칭.
                            const cols: Record<string, number[]> = {};
                            const pcols = (it.perk_columns ?? []).filter((c) => c.length > 0);
                            if (pcols.length > 0) {
                              pcols.forEach((col, ci) => {
                                const key = col[0].column_index ?? ci;
                                cols[String(key)] = col.map((p) => p.base_hash ?? p.plug_hash);
                              });
                            } else {
                              it.perks.forEach((p, i) => {
                                const key = p.column_index ?? i;
                                (cols[String(key)] ??= []).push(p.base_hash ?? p.plug_hash);
                              });
                            }
                            onLoadRoll(it.item_hash, cols, {
                              name: it.name, name_en: it.name_en, icon: it.icon,
                              weapon_subtype: it.weapon_subtype, default_damage_type: it.default_damage_type, tier: it.tier,
                            });
                          }}
                        >⬇</button>
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

            {tagScores && Object.keys(tagScores.tags).length > 0 && (
              <div className="tag-scores">
                <div className="tag-scores-title">{t.builder.tagScoresTitle}</div>
                {Object.entries(tagScores.tags).map(([tag, ts]) => {
                  const tcls = ts.classification;
                  const tcolor = tcls ? CLASS_COLOR[tcls] : "var(--border-strong)";
                  const hasRec = Object.keys(ts.recommended).length > 0;
                  return (
                    <div key={tag} className="tag-score-row">
                      <span className="tag-score-name">{tag}</span>
                      <span className="tag-score-val" style={{ color: tcolor }}>
                        {ts.score != null
                          ? `${ts.score}${tcls ? ` · ${t.scoring.classLabel[tcls as keyof typeof t.scoring.classLabel]}` : ""}`
                          : "—"}
                      </span>
                      {hasRec && (
                        <button
                          className="btn ghost sm"
                          title={t.builder.applyRecommended}
                          onClick={() => {
                            const sel: Record<number, number[]> = {};
                            for (const [k, v] of Object.entries(ts.recommended)) sel[Number(k)] = v;
                            setSelection(sel);
                          }}
                        >{t.builder.recommend}</button>
                      )}
                    </div>
                  );
                })}
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