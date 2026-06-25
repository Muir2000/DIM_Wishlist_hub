// 인게임 한국어 스탯 표기(매니페스트 ko 검증). 임의 번역 금지.
export const STAT_LABEL: Record<string, string> = {
  impact: "충격", range: "사거리", stability: "안정성", handling: "조작성",
  reload: "재장전 속도", magazine: "탄창", aim_assist: "조준 지원", recoil: "반동 방향",
  zoom: "확대/축소", rpm: "분당 발사 수", charge_time: "충전 시간", draw_time: "발사 시간",
  swing_speed: "스윙 속도", blast_radius: "폭발 반경", velocity: "투사체 속도",
};

const ORDER = [
  "impact", "range", "stability", "handling", "reload", "aim_assist",
  "magazine", "rpm", "recoil", "zoom", "charge_time", "draw_time",
  "blast_radius", "velocity", "swing_speed",
];
// 0~100 바로 표시할 스탯 (그 외는 raw 숫자만)
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
  // 베이스 스탯이 있는 키 + 델타만 있는 키 모두 표시
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
            <span className="stat-name">{STAT_LABEL[k] || k}</span>
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
