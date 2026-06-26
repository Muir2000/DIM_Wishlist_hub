import { useEffect, useState } from "react";
import { api } from "../api";
import type { ExportResult } from "../api";
import { useLanguage } from "../i18n";
import { useWishlist } from "../store";

export function WishlistPanel() {
  const { t } = useLanguage();
  const { rolls, title, description, setTitle, setDescription } = useWishlist();
  const [exp, setExp] = useState<ExportResult | null>(null);

  useEffect(() => {
    if (rolls.length === 0) {
      setExp(null);
      return;
    }
    const timeout = window.setTimeout(() => {
      api
        .exportList({ title, description, rolls: rolls.map((r) => r.input) })
        .then(setExp)
        .catch(() => setExp(null));
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [rolls, title, description]);

  function download() {
    if (!exp) return;
    const blob = new Blob([exp.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = exp.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="panel chamfer">
        <div className="panel-title">{t.wishlist.buildInfo}</div>
        <input
          className="text-input"
          placeholder={t.wishlist.titlePlaceholder}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ marginBottom: 10 }}
        />
        <textarea
          className="text-input"
          rows={2}
          placeholder={t.wishlist.descriptionPlaceholder}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="panel-title" style={{ margin: 0 }}>{t.wishlist.compileTitle} ({rolls.length} {t.wishlist.rolls})</span>
          {exp && <span className="panel-actions" style={{ fontFamily: "var(--font-mono)" }}>{exp.line_count} {t.wishlist.lines}</span>}
        </div>

        {rolls.length === 0 ? (
          <div className="empty" dangerouslySetInnerHTML={{ __html: t.wishlist.empty }} />
        ) : (
          <>
            {exp?.warning && <div className="warning-box">⚠ {exp.warning}</div>}
            <div className="code-preview">{exp?.content ?? t.wishlist.compiling}</div>
            <button
              className="btn primary"
              style={{ width: "100%", marginTop: 12 }}
              disabled={!exp}
              onClick={download}
            >
              ⬇ {t.wishlist.download}
            </button>
            <div className="instructions" style={{ marginTop: 14 }}>
              <strong>{t.wishlist.applyTitle}</strong> — {t.wishlist.applyBody}
              <code>is:wishlist</code>, <code>wishlistnotes:pvp</code>.
              <br />
              <span className="hint">{t.wishlist.ruleHint}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}