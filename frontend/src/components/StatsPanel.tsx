import { useLanguage } from "../i18n";
import { en } from "../i18n/en";

export const STAT_LABEL: Record<string, string> = en.stats;

const ORDER = [
  "impact", "range", "stability", "handling", "reload", "aim_assist",
  "magazine", "rpm", "recoil", "zoom", "charge_time", "draw_time",
  "blast_radius", "velocity", "swing_speed",
];

const BAR_STATS = new Set([
  "impact", "range", "stability", "handling", "reload",
  "aim_assist", "recoil", "zoom",
]);

export function StatsPanel({
  stats,
  deltas = {},
}: {
  stats: Record<string, number>;
  deltas?: Record<string, number>;
}) {
  const { t } = useLanguage();
  const allKeys = Array.from(new Set([...Object.keys(stats), ...Object.keys(deltas)]));
  const keys = allKeys.sort(
    (a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99),
  );

  return (
    <div className="stats-panel">
      {keys.map((k) => {
        const base = stats[k] ?? 0;
        const delta = deltas[k] ?? 0;
        const total = Math.min(100, Math.max(0, base + delta));
        const bar = BAR_STATS.has(k);

        return (
          <div className="stat-row" key={k}>
            <span className="stat-name">{t.stats[k as keyof typeof t.stats] || k}</span>
            <span className="stat-track" style={bar ? undefined : { background: "transparent" }}>
              {bar && (
                <>
                  <span
                    className="stat-fill"
                    style={{ width: `${Math.min(100, Math.max(0, base))}%` }}
                  />
                  {delta !== 0 && (
                    <span
                      className={`stat-delta-fill ${delta > 0 ? "pos" : "neg"}`}
                      style={{
                        left: delta > 0
                          ? `${Math.min(100, Math.max(0, base))}%`
                          : `${total}%`,
                        width: `${Math.abs(delta)}%`,
                      }}
                    />
                  )}
                </>
              )}
            </span>
            <span className="stat-val">
              {Math.round(total)}
              {delta !== 0 && (
                <span className={`stat-delta-badge ${delta > 0 ? "pos" : "neg"}`}>
                  {delta > 0 ? "▲" : "▼"}{Math.abs(delta)}
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}