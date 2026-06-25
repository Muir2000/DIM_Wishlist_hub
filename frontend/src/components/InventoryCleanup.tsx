import { useEffect, useState } from "react";
import { CLASS_COLOR, CLASS_LABEL, inventoryApi } from "../api";
import type { CleanupItem, InventoryStatus } from "../api";
import { useWishlist } from "../store";

export function InventoryCleanup() {
  const { activeProfile, rolls } = useWishlist();
  const [status, setStatus] = useState<InventoryStatus | null>(null);
  const [items, setItems] = useState<CleanupItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [onlyTrash, setOnlyTrash] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    inventoryApi.status().then(setStatus).catch(() => {});
  }, []);

  async function loadCleanup() {
    setLoading(true);
    setMsg("");
    try {
      const list = await inventoryApi.cleanup(activeProfile, rolls.map((r) => r.input));
      setItems(list);
      if (!activeProfile) setMsg("점수 프로필이 없어 중립 점수로 표시됩니다. '점수 기준' 탭에서 프로필을 활성화하세요.");
    } finally {
      setLoading(false);
    }
  }

  async function loadDemo() {
    const s = await inventoryApi.demo();
    setStatus(s);
    await loadCleanup();
  }

  async function sync() {
    setLoading(true);
    try {
      const s = await inventoryApi.sync();
      setStatus(s);
      await loadCleanup();
    } catch (e) {
      setMsg("동기화 실패: " + e);
    } finally {
      setLoading(false);
    }
  }

  async function exportTrash() {
    const res = await inventoryApi.exportTrashlist(activeProfile, rolls.map((r) => r.input));
    const blob = new Blob([res.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = res.filename;
    a.click();
    URL.revokeObjectURL(url);
    setMsg(`정리후보 ${res.trash_count}종을 트래시리스트로 내보냈습니다.`);
  }

  const shown = onlyTrash ? items.filter((i) => i.classification === "trash") : items;
  const trashCount = items.filter((i) => i.classification === "trash").length;

  return (
    <div>
      <div className="panel">
        <div className="panel-title">내 창고 — 장비 정리</div>

        {status && !status.oauth_configured && (
          <div className="warning-box" style={{ marginBottom: 12 }}>
            ⚠ Bungie OAuth 미설정. 실제 창고를 가져오려면 <code>.env</code> 에
            <code>BUNGIE_OAUTH_CLIENT_ID/SECRET</code> 를 설정하세요
            (bungie.net/en/Application, redirect: <code>/auth/bungie/callback</code>). 지금은 아래
            <strong> 데모 창고</strong>로 정리 기능을 체험할 수 있습니다.
          </div>
        )}

        <div className="controls-row">
          <button className="btn ghost" onClick={loadDemo} disabled={loading}>데모 창고 불러오기</button>
          {status?.oauth_configured && !status?.connected && (
            <a className="btn primary" href="/api/auth/bungie/login">Bungie 로그인</a>
          )}
          {status?.connected && status.membership_id !== "DEMO" && (
            <button className="btn primary" onClick={sync} disabled={loading}>창고 동기화</button>
          )}
          {items.length > 0 && (
            <>
              <button className="btn ghost" onClick={loadCleanup} disabled={loading}>다시 채점</button>
              <label className="toggle" style={{ cursor: "pointer" }}>
                <input type="checkbox" checked={onlyTrash} onChange={(e) => setOnlyTrash(e.target.checked)} />
                정리후보만 ({trashCount})
              </label>
              <button className="btn primary" onClick={exportTrash} style={{ marginLeft: "auto" }}>
                ⬇ 정리리스트 .txt
              </button>
            </>
          )}
        </div>
        <div className="hint">
          {activeProfile ? `활성 프로필: ${activeProfile.name}` : "활성 프로필 없음 (점수 기준 탭에서 선택)"}
          {status?.connected && ` · 창고 ${status.item_count}종`}
        </div>
        {msg && <div className="hint" style={{ marginTop: 8, color: "var(--primary-hover)" }}>{msg}</div>}
      </div>

      {shown.length > 0 && (
        <div className="panel">
          <div className="panel-title">점수순 (낮을수록 정리 권장)</div>
          {shown.map((it) => (
            <div key={it.item_instance_id} className="meta-row" style={{ gap: 12 }}>
              {it.icon ? <img src={it.icon} alt="" style={{ width: 36, height: 36, borderRadius: 4 }} />
                       : <div style={{ width: 36, height: 36, borderRadius: 4, background: "var(--bg)" }} />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{it.name} <span className="hint">{it.power ? `· ${it.power}` : ""}</span></div>
                <div className="hint">{it.perks.map((p) => p.name).filter(Boolean).join(" · ") || "(퍼크 없음)"}</div>
              </div>
              <div
                className="score-pill"
                style={{
                  color: CLASS_COLOR[it.classification || "trash"],
                  border: `1px solid ${CLASS_COLOR[it.classification || "trash"]}`,
                  fontSize: 13, padding: "4px 10px",
                }}
              >
                {it.score} · {CLASS_LABEL[it.classification || "trash"]}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
