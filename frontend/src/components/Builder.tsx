import { useEffect, useState } from "react";
import { api, CLASS_COLOR, CLASS_LABEL, ELEM_VAR, RARITY_VAR } from "../api";
import type { RollInput, ScoreResult, WeaponDetail, WeaponSummary } from "../api";
import { PerkGrid } from "./PerkGrid";
import { StatsPanel } from "./StatsPanel";
import { WishlistPanel } from "./WishlistPanel";
import { useWishlist } from "../store";

const TAGS = ["PvE", "PvP", "GM", "레이드"];

// 검색은 상단 헤더의 WeaponSearch 가 담당하고, 선택된 무기는 picked 로 전달된다.
export function Builder({ picked }: { picked: WeaponSummary | null }) {
  const { addRoll, activeProfile, rolls } = useWishlist();
  const [weapon, setWeapon] = useState<WeaponDetail | null>(null);
  const [selection, setSelection] = useState<Record<number, number[]>>({});
  const [trash, setTrash] = useState(false);
  const [wildcard, setWildcard] = useState(false);
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [score, setScore] = useState<ScoreResult | null>(null);
  // 퍽별 가중치(점수) — 선택과 무관하게 무기/프로필/위시리스트로 결정
  const [perkW, setPerkW] = useState<{
    weights: Record<number, number>;
    scale: number;
    signal: boolean;
    maxPossible: number;
    coverage: number;
    columnWeights: Record<string, number>;
    kinds: Record<number, string>;
  } | null>(null);

  // 활성 프로필이 있을 때, 현재 선택 퍽으로 실시간 점수 산정
  const selectedPerks = Object.values(selection).flat();
  useEffect(() => {
    if (!weapon || !activeProfile) {
      setScore(null);
      return;
    }
    const t = window.setTimeout(() => {
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
    return () => window.clearTimeout(t);
  }, [weapon, activeProfile, JSON.stringify(selectedPerks), rolls]);

  // 퍽별 가중치(점수) — 무기/프로필/위시리스트가 바뀔 때만 다시 계산(선택 무관)
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

  function resetBuilder() {
    setSelection({});
    setTrash(false);
    setWildcard(false);
    setTags([]);
    setNotes("");
  }

  // 헤더 검색에서 무기를 고르면(picked) 상세를 로드해 뷰어에 표시
  useEffect(() => {
    if (!picked) { setWeapon(null); return; }
    resetBuilder();
    let cancelled = false;
    api.weapon(picked.item_hash)
      .then((d) => { if (!cancelled) setWeapon(d); })
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

  function toggleTag(t: string) {
    setTags((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
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
      const input: RollInput = {
        weapon_hash: weapon.item_hash,
        columns,
        wildcard,
        trash,
        notes,
        tags,
        comment: weapon.name,
      };
      const res = await api.compile(input);
      const labelOf = (hash: number) => {
        for (const c of weapon.columns) {
          const p = c.perks.find((pp) => pp.plug_hash === hash);
          if (p) return p.name;
        }
        return String(hash);
      };
      const perkLabels = Object.values(selection).flat().map(labelOf);
      addRoll({
        input, weaponName: weapon.name, perkLabels, lines: res.lines,
        typeLabel: weapon.type_label, damageType: weapon.default_damage_type, tier: weapon.tier,
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

  return (
    <div className="builder-main">
      {/* 좌: 무기 헤더 + 퍼크 그리드 */}
      <div className="builder-col">
        {!weapon ? (
          <div className="panel">
            <div className="empty">상단 검색창에서 무기를 검색·선택하면 여기에 퍼크 그리드가 표시됩니다.</div>
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
                <div className="w-name">{weapon.name}</div>
                <div className="w-sub">
                  {weapon.type_label}
                  {weapon.damage_label ? <> · <span className="elem-name">{weapon.damage_label}</span></> : ""}
                  {weapon.slot ? ` · ${weapon.slot}` : ""}
                  {weapon.season_number ? (
                    <> · <span className="w-season" title={`시즌 ${weapon.season_number}: ${weapon.season_name ?? ""}`}>
                      {weapon.watermark && <img className="w-season-wm" src={weapon.watermark} alt="" />}
                      시즌 {weapon.season_number}{weapon.season_name ? ` · ${weapon.season_name}` : ""}
                    </span></>
                  ) : null}
                </div>
                {weapon.season_count && weapon.season_count > 1 && (
                  <div className="variant-note" title="이 무기는 시즌(복각)마다 퍽풀이 다릅니다. 지금 보는 것은 이 시즌의 퍽풀입니다. 같은 시즌 홀로포일은 동일한 퍽풀을 공유하며, 위시리스트는 굴릴 수 있는 모든 시즌에 자동 적용됩니다.">
                    ⛓ 이 무기는 <b>{weapon.season_count}개 시즌</b>으로 출시되었고 <b>시즌마다 퍽풀이 다릅니다</b>.
                    {weapon.has_holofoil && <> 이 시즌엔 홀로포일 ✦(동일 퍽롤)도 있습니다.</>}
                    {" "}지금은 <b>이 시즌</b>의 퍽풀이며, 위시리스트는 해당 퍽을 굴릴 수 있는 시즌 전체에 적용됩니다.
                  </div>
                )}
              </div>
            </div>

            <div className="panel">
              <div className="panel-head">
                <span className="panel-title" style={{ margin: 0 }}>퍼크 선택</span>
                <span className="panel-actions">열당 여러 개 = OR (줄 전개)</span>
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
          </>
        )}
      </div>

      {/* 우: 현재 롤(점수·옵션·추가) + 리스트 컴파일 */}
      <aside className="roll-side">
        {weapon && (
          <div className="panel roll-panel">
            <div className="panel-title" style={{ marginTop: 0 }}>현재 롤</div>

            {/* 총점 — 가장 눈에 띄게 상단에 */}
            {!activeProfile ? (
              <div className="score-hint">
                점수 기준(프로필)을 활성화하면 이 롤의 점수가 표시됩니다. (메뉴 → 점수 기준)
              </div>
            ) : score && score.score != null && cls ? (
              <div className="roll-score" style={{ ["--score-color" as any]: CLASS_COLOR[cls] }}>
                <div className="rs-top">
                  <span className="rs-num">{score.score}</span>
                  <span className="rs-max">/100</span>
                  <span className="rs-cls">{CLASS_LABEL[cls]}</span>
                </div>
                <div className="rs-bd">
                  {score.breakdown.perk != null && `퍽 ${score.breakdown.perk}`}
                  {score.breakdown.synergy != null && ` · 조합 +${score.breakdown.synergy}`}
                </div>
              </div>
            ) : (
              <div className="score-hint">
                이 무기(또는 종류)의 위시리스트 롤이 있어야 점수가 매겨집니다.
              </div>
            )}

            {cov != null && cov < 1 && (
              <div className="coverage-note" title="이 무기의 위시리스트가 없어 같은 종류·프레임 기준으로만 평가됩니다. 무기별 롤을 등록하면 최대 100%까지 평가됩니다.">
                ⓘ 이 무기 위시리스트 미등록 — <b>종류·프레임 기준</b>(최대 {Math.round(cov * 100)}%)
              </div>
            )}

            {/* 롤 옵션 */}
            <div className="controls-row" style={{ marginTop: 14 }}>
              <button
                className={`toggle trash ${trash ? "on" : ""}`}
                onClick={() => {
                  setTrash((t) => !t);
                  if (!trash) setWildcard(false);
                }}
              >
                👎 트래시롤
              </button>
              <button
                className={`toggle wild ${wildcard ? "on" : ""}`}
                onClick={() => {
                  setWildcard((w) => !w);
                  if (!wildcard) setTrash(false);
                }}
              >
                ✷ 와일드카드
              </button>
            </div>
            <div className="tag-chips" style={{ marginBottom: 12 }}>
              {TAGS.map((t) => (
                <button
                  key={t}
                  className={`chip ${tags.includes(t) ? "on" : ""}`}
                  onClick={() => toggleTag(t)}
                >
                  {t}
                </button>
              ))}
            </div>

            <textarea
              className="text-input"
              rows={2}
              placeholder="메모 (#notes:) — 선택 사항"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />

            <div className="hint" style={{ marginTop: 10 }}>
              {wildcard ? "와일드카드: item=-69420 " : trash ? "트래시롤: 음수 해시 " : ""}
              {colCount > 0 ? `· ${comboCount}개 줄로 전개` : "· 퍼크 미선택"}
            </div>
            <button
              className="btn primary"
              style={{ width: "100%", marginTop: 10 }}
              disabled={!canAdd || busy}
              onClick={add}
            >
              ＋ 위시리스트에 추가
            </button>
          </div>
        )}

        <WishlistPanel />
      </aside>
    </div>
  );
}
