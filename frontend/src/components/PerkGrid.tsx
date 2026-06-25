import type { WeaponDetail } from "../api";
import { perkTier, PERK_TIER_COLOR } from "../api";
import { PerkIcon } from "./PerkIcon";
import { STAT_LABEL } from "./StatsPanel";

export function PerkGrid({
  weapon,
  selection,
  onToggle,
  weights,
  scale = 50,
  maxPossible,
  columnWeights,
  kinds,
}: {
  weapon: WeaponDetail;
  selection: Record<number, number[]>;
  onToggle: (col: number, hash: number) => void;
  weights?: Record<number, number> | null; // plug_hash → 가중치 (활성 프로필+위시리스트)
  scale?: number;                           // 배지 점수 = 가중치 * scale (desirability)
  maxPossible?: number;                     // 동적 만점(열 비중 합) — 기여 환산용
  columnWeights?: Record<string, number>;   // 열종류 → 비중
  kinds?: Record<number, string>;           // plug_hash → 열종류
}) {
  return (
    <div className="perk-columns">
      {weapon.columns.map((col) => {
        const maxPop = Math.max(1, ...col.perks.map((p) => p.popularity));
        const picked = selection[col.index] ?? [];
        return (
          <div className="perk-column" key={col.index}>
            <div className="col-label">{col.label}</div>
            {col.perks.map((p) => {
              const isSel = picked.includes(p.plug_hash);
              const popPct = Math.round((p.popularity / maxPop) * 100);
              const desc = p.description || p.description_en;
              // 퍽 점수(가중치 환산) — 신호가 있을 때만, 0점은 표시 생략
              const w = weights ? weights[p.plug_hash] : undefined;
              const points = w != null ? Math.round(w * scale) : null;
              const tier = points != null && points !== 0 ? perkTier(points) : null;
              const tierColor = tier ? PERK_TIER_COLOR[tier] : undefined;
              // 이 무기 점수 기여(%) = 열 비중 * 가중치 * 100 / 동적 만점
              const kind = kinds ? kinds[p.plug_hash] : undefined;
              const cw = kind && columnWeights ? columnWeights[kind] : undefined;
              const contrib =
                w != null && cw != null && maxPossible
                  ? Math.round((cw * w * 100) / maxPossible)
                  : null;
              return (
                <div
                  key={p.plug_hash}
                  className={`perk-tile-wrap${tier ? ` scored tier-${tier}` : ""}`}
                  style={tierColor ? ({ ["--perk-tier-color" as any]: tierColor } as React.CSSProperties) : undefined}
                >
                  <button
                    className={`perk-tile ${isSel ? "selected" : ""}`}
                    onClick={() => onToggle(col.index, p.plug_hash)}
                  >
                    {p.popularity > 0 && (
                      <span className="pop-bar" style={{ width: `${popPct}%` }} />
                    )}
                    <PerkIcon perk={p} kind={col.kind} />
                    <span className="perk-info">
                      <span className="perk-name">{p.name}</span>
                      <span className="perk-flags">
                        {p.is_curated && <span className="flag curated">큐레이티드</span>}
                        {!p.currently_can_roll && <span className="flag retired">단종</span>}
                        {p.popularity > 0 && <span className="flag pop">{p.popularity}</span>}
                      </span>
                      {p.stats && Object.keys(p.stats).length > 0 && (
                        <span className="perk-delta">
                          {Object.entries(p.stats).map(([k, v]) => (
                            <span key={k} className={v > 0 ? "up" : "down"}>
                              {STAT_LABEL[k] || k} {v > 0 ? "+" : ""}{v}{" "}
                            </span>
                          ))}
                        </span>
                      )}
                    </span>
                    {points != null && points !== 0 && (
                      <span
                        className={`perk-score tier-${tier}`}
                        title={`이 퍽의 위시리스트 기반 점수 ${points > 0 ? "+" : ""}${points} (가중치 ${w})`}
                      >
                        {points > 0 ? "+" : ""}{points}
                      </span>
                    )}
                  </button>
                  {desc && (
                    <div className="perk-tooltip">
                      <div className="perk-tooltip-name">{p.name}</div>
                      <div className="perk-tooltip-desc">{desc}</div>
                      {points != null && points !== 0 && (
                        <div className={`perk-tooltip-score tier-${tier}`}>
                          퍽 선호도 {points > 0 ? "+" : ""}{points}
                          {contrib != null && contrib !== 0 && (
                            <span className="perk-tooltip-contrib">
                              · 이 무기 점수 기여 {contrib > 0 ? "+" : ""}{contrib}
                            </span>
                          )}
                        </div>
                      )}
                      {p.stats && Object.keys(p.stats).length > 0 && (
                        <div className="perk-tooltip-stats">
                          {Object.entries(p.stats).map(([k, v]) => (
                            <span key={k} className={`perk-tooltip-stat ${v > 0 ? "pos" : "neg"}`}>
                              {STAT_LABEL[k] || k} {v > 0 ? "+" : ""}{v}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
