import { useEffect, useState } from "react";
import { api, ELEM_VAR } from "../api";
import type { TopWeapon } from "../api";

// damage_label(한국어) → 원소 키 (메타 응답엔 라벨만 있어 역매핑). 인게임 공식 표기 기준.
const DAMAGE_LABEL_TO_KEY: Record<string, string> = {
  물리: "Kinetic", 전기: "Arc", 태양: "Solar", 공허: "Void",
  시공: "Stasis", 초월: "Strand", 프리즘: "Prismatic",
};

export function MetaDashboard() {
  const [rows, setRows] = useState<TopWeapon[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.topWeapons(20).then(setRows).catch((e) => setErr(String(e)));
  }, []);

  const max = Math.max(1, ...rows.map((r) => r.total));

  return (
    <div className="page-narrow">
      <h1 style={{ fontSize: 32, textTransform: "uppercase", margin: "0 0 6px" }}>커뮤니티 메타</h1>
      <p style={{ color: "var(--text-muted)", fontSize: 14, margin: "0 0 24px" }}>
        현재 시즌 최다 위시리스트 무기 · <span style={{ color: "var(--community)" }}>voltron.txt</span> 부트스트랩 집계
      </p>

      <div className="panel" style={{ padding: 0 }}>
        <div className="panel-title" style={{ padding: "14px 16px 0", margin: 0 }}>TOP 무기 (추천 빈도)</div>
        {err && <div className="empty">데이터를 불러오지 못했습니다: {err}</div>}
        {!err && rows.length === 0 && <div className="empty">집계 데이터가 아직 없습니다.</div>}
        {rows.map((r, i) => {
          const elemKey = r.damage_label ? DAMAGE_LABEL_TO_KEY[r.damage_label] : undefined;
          const elemVar = elemKey ? ELEM_VAR[elemKey] : undefined;
          return (
            <div className="meta-row" key={r.item_hash}>
              <span className="rank">{i + 1}</span>
              <span className="elem-stripe" style={{ ["--elem-color" as any]: elemVar ? `var(${elemVar})` : undefined }} />
              <span style={{ minWidth: 150 }}>
                <span style={{ display: "block", fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em" }}>
                  {r.name}
                </span>
                <span style={{ display: "block", fontSize: 11, color: "var(--text-faint)" }}>
                  {r.type_label}{r.damage_label ? ` · ${r.damage_label}` : ""}
                </span>
              </span>
              <div className="meta-bar-wrap">
                <div className="meta-bar"><span style={{ width: `${Math.round((r.total / max) * 100)}%` }} /></div>
              </div>
              <span className="meta-total">{r.total.toLocaleString()}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
