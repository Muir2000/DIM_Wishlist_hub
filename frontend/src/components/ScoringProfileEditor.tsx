import { useEffect, useState } from "react";
import { api } from "../api";
import type { DeriveContext, DeriveResult, ScoringProfile } from "../api";
import { useWishlist } from "../store";
import { STAT_LABEL } from "./StatsPanel";

const STAT_KEYS = ["handling", "range", "stability", "reload", "aim_assist", "impact", "recoil", "zoom"];
const KIND_LABEL: Record<string, string> = { type: "종류", frame: "프레임", weapon: "무기" };
const DEFAULT_SCOPE_BLEND = { weapon: 0.6, frame: 0.25, type: 0.15 };
const DEFAULT_COLUMN_WEIGHTS = { trait: 1.0, barrel: 0.35, magazine: 0.35, origin: 0.2, intrinsic: 0.0 };
const SCOPE_LABEL: Record<string, string> = { weapon: "동일 무기", frame: "동일 프레임", type: "동일 종류" };
const COL_LABEL: Record<string, string> = { trait: "특성", barrel: "총열", magazine: "탄창", origin: "기원", intrinsic: "고유" };

function blankProfile(): ScoringProfile {
  return {
    id: null,
    name: "새 점수 기준",
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
  const { activeProfile, setActiveProfile, rolls } = useWishlist();
  const [profiles, setProfiles] = useState<ScoringProfile[]>([]);
  const [draft, setDraft] = useState<ScoringProfile>(activeProfile ?? blankProfile());
  const [status, setStatus] = useState("");
  const [contexts, setContexts] = useState<DeriveContext[]>([]);

  useEffect(() => {
    refresh();
  }, []);

  function refresh() {
    api.listProfiles().then(setProfiles).catch(() => {});
  }

  function applyDerived(res: DeriveResult) {
    const scopeCount = Object.keys(res.context_weights).length;
    if (!scopeCount) {
      setStatus(`위시리스트에서 컨텍스트를 찾지 못했습니다 (롤 ${res.rolls_parsed}개). 무기별 롤이 필요합니다.`);
      return;
    }
    setDraft((d) => ({
      ...d,
      context_weights: res.context_weights,
      context_synergies: res.context_synergies,
    }));
    setContexts(res.contexts);
    const combos = res.contexts.reduce((n, c) => n + c.combos.length, 0);
    setStatus(`위시리스트 학습 완료 — 컨텍스트 ${scopeCount}개, 조합 ${combos}개 (롤 ${res.rolls_parsed}개).`);
  }

  async function useCurrentWishlist() {
    if (!rolls.length) {
      setStatus("현재 위시리스트가 비어 있습니다. '빌더'에서 롤을 추가하세요.");
      return;
    }
    applyDerived(await api.deriveWeights({ rolls: rolls.map((r) => r.input) }));
  }

  function uploadWishlist(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    f.text().then(async (text) => applyDerived(await api.deriveWeights({ text })));
    e.target.value = "";
  }

  function clearContexts() {
    setDraft((d) => ({ ...d, context_weights: {}, context_synergies: {} }));
    setContexts([]);
  }

  function setStat(k: string, v: number) {
    setDraft((d) => {
      const sw = { ...d.stat_weights };
      if (v === 0) delete sw[k];
      else sw[k] = v;
      return { ...d, stat_weights: sw };
    });
  }

  async function save() {
    const saved = await api.saveProfile(draft);
    setDraft(saved);
    setActiveProfile(saved);
    refresh();
    setStatus(`저장됨: ${saved.name}`);
  }

  async function del(id?: string | null) {
    if (!id) return;
    await api.deleteProfile(id);
    if (draft.id === id) setDraft(blankProfile());
    if (activeProfile?.id === id) setActiveProfile(null);
    refresh();
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
    const f = e.target.files?.[0];
    if (!f) return;
    f.text().then((t) => {
      try {
        const p = JSON.parse(t) as ScoringProfile;
        p.id = null; // 가져오면 새 프로필로 저장
        setDraft({ ...blankProfile(), ...p, id: null });
        setStatus(`가져옴: ${p.name}`);
      } catch {
        setStatus("JSON 파싱 실패");
      }
    });
  }

  return (
    <div className="layout">
      <div>
        <div className="panel">
          <div className="panel-title">점수 기준 편집</div>
          <input
            className="text-input"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="프로필 이름"
          />

          <div className="panel-title" style={{ marginTop: 16 }}>스탯 가중치 (0 = 미사용)</div>
          {STAT_KEYS.map((k) => (
            <div className="weight-row" key={k}>
              <span className="weight-name">{STAT_LABEL[k] || k}</span>
              <input
                type="range" min={0} max={3} step={0.5}
                value={draft.stat_weights[k] ?? 0}
                onChange={(e) => setStat(k, Number(e.target.value))}
              />
              <span className="weight-val">{(draft.stat_weights[k] ?? 0).toFixed(1)}</span>
            </div>
          ))}

          <div className="panel-title" style={{ marginTop: 16 }}>위시리스트로 컨텍스트 학습 (종류·프레임·무기별)</div>
          <div className="hint" style={{ marginBottom: 8 }}>
            위시리스트를 분석해 <strong>무기 종류·프레임·개별 무기</strong>별로 퍽 가중치와 인기 조합을 학습합니다.
            같은 퍽이라도 무기에 따라 점수가 달라집니다 (예: 핸드 캐논의 무법자).
          </div>
          <div className="controls-row" style={{ flexWrap: "wrap" }}>
            <button className="btn ghost" onClick={useCurrentWishlist}>
              현재 위시리스트 사용 ({rolls.length}롤)
            </button>
            <label className="btn ghost" style={{ cursor: "pointer" }}>
              DIM 위시리스트 .txt 업로드
              <input type="file" accept=".txt,text/plain" style={{ display: "none" }} onChange={uploadWishlist} />
            </label>
            {Object.keys(draft.context_weights || {}).length > 0 && (
              <button className="btn ghost" onClick={clearContexts}>학습 지우기</button>
            )}
          </div>

          {contexts.length > 0 ? (
            <div className="ctx-list">
              {contexts.map((c) => (
                <div className="ctx-group" key={c.scope}>
                  <div className="ctx-head">
                    <span className="ctx-kind">{KIND_LABEL[c.kind] || c.kind}</span>
                    <span className="ctx-label">{c.label}</span>
                  </div>
                  <div className="ctx-perks">
                    {c.weights.slice(0, 6).map((w) => (
                      <span key={w.plug_hash} className={`ctx-pill ${w.weight >= 0 ? "up" : "down"}`}>
                        {w.name || w.plug_hash} {w.weight > 0 ? "+" : ""}{w.weight}
                      </span>
                    ))}
                  </div>
                  {c.combos.length > 0 && (
                    <div className="ctx-combos">
                      조합: {c.combos.map((cb, i) => (
                        <span key={i} className="ctx-combo">{cb.perks.map((p) => p.name || p.plug_hash).join("+")}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            Object.keys(draft.context_weights || {}).length > 0 && (
              <div className="hint" style={{ marginTop: 8 }}>
                컨텍스트 {Object.keys(draft.context_weights || {}).length}개 등록됨 (저장된 프로필). 다시 학습하면 상세가 표시됩니다.
              </div>
            )
          )}

          <div className="panel-title" style={{ marginTop: 16 }}>점수 비중 (가중)</div>
          <div className="hint" style={{ marginBottom: 8 }}>
            점수는 <strong>동일 무기·프레임·종류</strong> 위시리스트를 각각 계산해 아래 비중으로 합산하고,
            <strong>열(총열/탄창/특성)</strong>별 기여를 다르게 둡니다. 무기별 위시리스트가 없으면 종류·프레임
            비중까지만 반영(낮은 신뢰). 세부 조정은 JSON 가져오기로. (기본값 적용 중)
          </div>
          <div className="blend-info">
            <span className="blend-label">스코프</span>
            {Object.entries(draft.scope_blend ?? DEFAULT_SCOPE_BLEND).map(([k, v]) => (
              <span key={k} className="blend-pill">{SCOPE_LABEL[k] || k} {Math.round(v * 100)}%</span>
            ))}
          </div>
          <div className="blend-info">
            <span className="blend-label">열 비중</span>
            {Object.entries(draft.column_weights ?? DEFAULT_COLUMN_WEIGHTS)
              .filter(([, v]) => v > 0)
              .map(([k, v]) => (
                <span key={k} className="blend-pill">{COL_LABEL[k] || k} ×{v}</span>
              ))}
          </div>

          <div className="controls-row" style={{ marginTop: 14 }}>
            <label className="toggle" style={{ cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={draft.use_wishlist_weights}
                onChange={(e) => setDraft({ ...draft, use_wishlist_weights: e.target.checked })}
              />
              위시리스트 자동 가중치 (활성 위시리스트 실시간 반영)
            </label>
          </div>

          <div className="controls-row">
            <label className="filter-stat">갓롤 ≥
              <input type="number" className="text-input"
                     value={draft.thresholds.god}
                     onChange={(e) => setDraft({ ...draft, thresholds: { ...draft.thresholds, god: Number(e.target.value) } })} />
            </label>
            <label className="filter-stat">쓸만함 ≥
              <input type="number" className="text-input"
                     value={draft.thresholds.viable}
                     onChange={(e) => setDraft({ ...draft, thresholds: { ...draft.thresholds, viable: Number(e.target.value) } })} />
            </label>
          </div>

          <div className="controls-row" style={{ marginTop: 12, gap: 8, flexWrap: "wrap" }}>
            <button className="btn primary" onClick={save}>저장 & 활성화</button>
            <button className="btn ghost" onClick={() => setDraft(blankProfile())}>새로 만들기</button>
            <button className="btn ghost" onClick={exportJson}>JSON 내보내기</button>
            <label className="btn ghost" style={{ cursor: "pointer" }}>
              JSON 가져오기
              <input type="file" accept="application/json" style={{ display: "none" }} onChange={importJson} />
            </label>
          </div>
          {status && <div className="hint" style={{ marginTop: 8, color: "var(--success)" }}>{status}</div>}
          <div className="hint" style={{ marginTop: 8 }}>
            퍽 조합 시너지·수동 퍽 가중치는 JSON(가져오기)으로 편집할 수 있습니다.
          </div>
        </div>
      </div>

      <div>
        <div className="panel chamfer">
          <div className="panel-title">저장된 프로필</div>
          {activeProfile && (
            <div className="hint" style={{ marginBottom: 8 }}>
              활성: <strong style={{ color: "var(--primary-hover)" }}>{activeProfile.name}</strong>
            </div>
          )}
          {profiles.length === 0 && <div className="empty">저장된 프로필이 없습니다.</div>}
          {profiles.map((p) => (
            <div key={p.id} className={`roll-item ${activeProfile?.id === p.id ? "wild" : ""}`}>
              <div className="r-main">
                <div className="r-name">{p.name}</div>
                <div className="r-perks">
                  스탯 {Object.keys(p.stat_weights || {}).length}개
                  {Object.keys(p.context_weights || {}).length > 0 ? ` · 컨텍스트 ${Object.keys(p.context_weights || {}).length}개` : ""}
                  {p.use_wishlist_weights ? " · 위시리스트 가중" : ""}
                </div>
              </div>
              <button className="btn ghost" style={{ padding: "4px 8px", fontSize: 12 }} onClick={() => { setDraft(p); setActiveProfile(p); }}>활성화</button>
              <button className="icon-btn" title="삭제" onClick={() => del(p.id)}>✕</button>
            </div>
          ))}
          <button className="btn ghost" style={{ marginTop: 8 }} onClick={() => setActiveProfile(null)}>
            점수 끄기
          </button>
        </div>
      </div>
    </div>
  );
}
