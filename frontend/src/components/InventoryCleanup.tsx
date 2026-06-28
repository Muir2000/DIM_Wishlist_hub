import { useEffect, useState } from "react";
import { CLASS_COLOR, inventoryApi } from "../api";
import type { CleanupItem, InventoryStatus } from "../api";
import { displayName, formatTemplate, useLanguage } from "../i18n";
import { useWishlist } from "../store";

export function InventoryCleanup() {
  const { language, t } = useLanguage();
  const { activeProfile, scoringProfile, rolls } = useWishlist();
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
      const list = await inventoryApi.cleanup(scoringProfile, rolls.map((r) => r.input));
      setItems(list);
      if (!activeProfile) setMsg(t.vault.neutralProfile);
    } finally {
      setLoading(false);
    }
  }

  async function loadDemo() {
    const next = await inventoryApi.demo();
    setStatus(next);
    await loadCleanup();
  }

  async function sync() {
    setLoading(true);
    try {
      const next = await inventoryApi.sync();
      setStatus(next);
      await loadCleanup();
    } catch (e) {
      setMsg(`${t.vault.syncFailed}: ${e}`);
    } finally {
      setLoading(false);
    }
  }

  async function exportTrash() {
    const res = await inventoryApi.exportTrashlist(scoringProfile, rolls.map((r) => r.input));
    const blob = new Blob([res.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = res.filename;
    a.click();
    URL.revokeObjectURL(url);
    setMsg(formatTemplate(t.vault.exported, { count: res.trash_count }));
  }

  const shown = onlyTrash ? items.filter((i) => i.classification === "trash") : items;
  const trashCount = items.filter((i) => i.classification === "trash").length;

  return (
    <div>
      <div className="panel">
        <div className="panel-title">{t.vault.title}</div>

        {status && !status.oauth_configured && (
          <div className="warning-box" style={{ marginBottom: 12 }}>
            ⚠ {t.vault.oauthWarning}
          </div>
        )}

        <div className="controls-row">
          <button className="btn ghost" onClick={loadDemo} disabled={loading}>{t.vault.loadDemo}</button>
          {status?.oauth_configured && !status?.connected && (
            <a className="btn primary" href="/api/auth/bungie/login">{t.vault.login}</a>
          )}
          {status?.connected && status.membership_id !== "DEMO" && (
            <button className="btn primary" onClick={sync} disabled={loading}>{t.vault.sync}</button>
          )}
          {items.length > 0 && (
            <>
              <button className="btn ghost" onClick={loadCleanup} disabled={loading}>{t.vault.rescore}</button>
              <label className="toggle" style={{ cursor: "pointer" }}>
                <input type="checkbox" checked={onlyTrash} onChange={(e) => setOnlyTrash(e.target.checked)} />
                {t.vault.trashOnly} ({trashCount})
              </label>
              <button className="btn primary" onClick={exportTrash} style={{ marginLeft: "auto" }}>
                ⬇ {t.vault.exportTrash}
              </button>
            </>
          )}
        </div>
        <div className="hint">
          {activeProfile ? `${t.vault.activeProfile}: ${activeProfile.name}` : t.vault.noProfile}
          {status?.connected && ` · ${status.item_count} ${t.vault.vaultItems}`}
        </div>
        {msg && <div className="hint" style={{ marginTop: 8, color: "var(--primary-hover)" }}>{msg}</div>}
      </div>

      {shown.length > 0 && (
        <div className="panel">
          <div className="panel-title">{t.vault.scoreOrder}</div>
          {shown.map((item) => {
            const cls = item.classification || "trash";
            return (
              <div key={item.item_instance_id} className="meta-row" style={{ gap: 12 }}>
                {item.icon ? <img src={item.icon} alt="" style={{ width: 36, height: 36, borderRadius: 4 }} />
                         : <div style={{ width: 36, height: 36, borderRadius: 4, background: "var(--bg)" }} />}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{displayName(item, language)} <span className="hint">{item.power ? `· ${item.power}` : ""}</span></div>
                  <div className="hint">{item.perks.map((p) => displayName(p, language)).filter(Boolean).join(" · ") || t.vault.noPerks}</div>
                </div>
                <div
                  className="score-pill"
                  style={{
                    color: CLASS_COLOR[cls],
                    border: `1px solid ${CLASS_COLOR[cls]}`,
                    fontSize: 13, padding: "4px 10px",
                  }}
                >
                  {item.score} · {t.scoring.classLabel[cls as keyof typeof t.scoring.classLabel]}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}