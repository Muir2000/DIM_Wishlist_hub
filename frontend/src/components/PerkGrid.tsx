import type { WeaponDetail } from "../api";
import { perkTier, PERK_TIER_COLOR } from "../api";
import { columnKindLabel, displayName, useLanguage } from "../i18n";
import { PerkIcon } from "./PerkIcon";

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
  weights?: Record<number, number> | null;
  scale?: number;
  maxPossible?: number;
  columnWeights?: Record<string, number>;
  kinds?: Record<number, string>;
}) {
  const { language, t } = useLanguage();
  return (
    <div className="perk-columns">
      {weapon.columns.map((col) => {
        const maxPop = Math.max(1, ...col.perks.map((p) => p.popularity));
        const picked = selection[col.index] ?? [];
        return (
          <div className="perk-column" key={col.index}>
            <div className="col-label">{columnKindLabel(col.kind, t, col.label)}</div>
            {col.perks.map((p) => {
              const isSel = picked.includes(p.plug_hash);
              const popPct = Math.round((p.popularity / maxPop) * 100);
              const name = displayName(p, language);
              const desc = language === "en" ? (p.description_en || p.description) : (p.description || p.description_en);
              const w = weights ? weights[p.plug_hash] : undefined;
              const points = w != null ? Math.round(w * scale) : null;
              const tier = points != null && points !== 0 ? perkTier(points) : null;
              const tierColor = tier ? PERK_TIER_COLOR[tier] : undefined;
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
                      <span className="perk-name">{name}</span>
                      <span className="perk-flags">
                        {p.is_curated && <span className="flag curated">{t.labels.curated}</span>}
                        {!p.currently_can_roll && <span className="flag retired">{t.labels.retired}</span>}
                        {p.popularity > 0 && <span className="flag pop">{p.popularity}</span>}
                      </span>
                      {p.stats && Object.keys(p.stats).length > 0 && (
                        <span className="perk-delta">
                          {Object.entries(p.stats).map(([k, v]) => (
                            <span key={k} className={v > 0 ? "up" : "down"}>
                              {t.stats[k as keyof typeof t.stats] || k} {v > 0 ? "+" : ""}{v}{" "}
                            </span>
                          ))}
                        </span>
                      )}
                    </span>
                    {points != null && points !== 0 && (
                      <span
                        className={`perk-score tier-${tier}`}
                        title={`${t.labels.perk} ${t.labels.score} ${points > 0 ? "+" : ""}${points} (weight ${w})`}
                      >
                        {points > 0 ? "+" : ""}{points}
                      </span>
                    )}
                  </button>
                  {desc && (
                    <div className="perk-tooltip">
                      <div className="perk-tooltip-name">{name}</div>
                      <div className="perk-tooltip-desc">{desc}</div>
                      {points != null && points !== 0 && (
                        <div className={`perk-tooltip-score tier-${tier}`}>
                          {t.labels.perk} preference {points > 0 ? "+" : ""}{points}
                          {contrib != null && contrib !== 0 && (
                            <span className="perk-tooltip-contrib">
                              · weapon score contribution {contrib > 0 ? "+" : ""}{contrib}
                            </span>
                          )}
                        </div>
                      )}
                      {p.stats && Object.keys(p.stats).length > 0 && (
                        <div className="perk-tooltip-stats">
                          {Object.entries(p.stats).map(([k, v]) => (
                            <span key={k} className={`perk-tooltip-stat ${v > 0 ? "pos" : "neg"}`}>
                              {t.stats[k as keyof typeof t.stats] || k} {v > 0 ? "+" : ""}{v}
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