import { useRef, useState } from "react";
import { api, ELEM_VAR, RARITY_VAR } from "../api";
import type { ImportResult } from "../api";
import { formatTemplate, useLanguage } from "../i18n";
import { useWishlist } from "../store";

export function ListRail() {
  const { language, t } = useLanguage();
  const { rolls, addRolls, removeRoll, clear, setTitle, setDescription } = useWishlist();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  function focusSearch() {
    const el = document.querySelector<HTMLInputElement>(".search-input");
    el?.focus();
    el?.scrollIntoView({ block: "center" });
  }

  function applyImport(res: ImportResult, replace: boolean) {
    if (replace) clear();
    addRolls(res.rolls.map((ir) => ({
      input: ir.input,
      weaponName: language === "en" ? (ir.weapon_name_en || ir.weapon_name) : ir.weapon_name,
      perkLabels: language === "en" ? (ir.perk_labels_en?.length ? ir.perk_labels_en : ir.perk_labels) : ir.perk_labels,
      lines: ir.lines,
      typeLabel: ir.type_label,
      damageType: ir.damage_type,
      tier: ir.tier,
    })));
    if (res.title) setTitle(res.title);
    if (res.description) setDescription(res.description);
    const extra = [
      res.unknown_weapons ? `${t.list.missingWeapons} ${res.unknown_weapons}` : "",
      res.wildcard ? `${t.list.wildcard} ${res.wildcard}` : "",
      res.skipped_lines ? `${t.list.skippedLines} ${res.skipped_lines}` : "",
    ].filter(Boolean).join(" · ");
    setStatus(`${formatTemplate(t.list.imported, { count: res.imported })}${extra ? ` (${t.list.excluded}: ${extra})` : ""}`);
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setStatus(t.list.importing);
    try {
      const text = await file.text();
      const res = await api.importWishlist(text);
      if (res.imported === 0) {
        setStatus(`${t.list.importNone} (${t.list.skippedLines} ${res.skipped_lines}, ${t.list.missingWeapons} ${res.unknown_weapons})`);
        return;
      }
      const replace = rolls.length > 0
        ? window.confirm(formatTemplate(t.list.replaceConfirm, { count: res.imported }))
        : true;
      applyImport(res, replace);
    } catch (err) {
      setStatus(`${t.list.importFailed}: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="list-rail">
      <div className="rail-head">
        <span className="rail-title">{t.list.title}</span>
        <button className="rail-add" title={t.list.importWishlist} disabled={busy}
                onClick={() => fileRef.current?.click()}>⤓</button>
        <button className="rail-add" title={t.list.addWeapon} onClick={focusSearch}>+</button>
        <input ref={fileRef} type="file" accept=".txt,text/plain" hidden onChange={onFile} />
      </div>
      {status && <div className="rail-status">{status}</div>}
      <div className="rail-list">
        {rolls.length === 0 && (
          <div className="rail-empty" dangerouslySetInnerHTML={{ __html: t.list.empty }} />
        )}
        {rolls.map((roll) => {
          const elemVar = roll.damageType ? ELEM_VAR[roll.damageType] : undefined;
          const rarityVar = roll.tier ? RARITY_VAR[roll.tier] : undefined;
          const cls = roll.input.wildcard ? "wild" : roll.input.trash ? "trash" : "";
          return (
            <div key={roll.id} className={`rail-item ${cls}`}>
              <span
                className="w-thumb"
                style={{
                  width: 32, height: 32,
                  background: `linear-gradient(135deg, ${rarityVar ? `var(${rarityVar})` : "#333"}, #1a1f29)`,
                  boxShadow: `inset 0 0 0 1px ${rarityVar ? `var(${rarityVar})` : "#333"}`,
                }}
              >
                <span className="elem" style={{ ["--elem-color" as any]: elemVar ? `var(${elemVar})` : undefined }} />
              </span>
              <span style={{ minWidth: 0, flex: 1 }}>
                <span className="r-name">
                  {roll.input.wildcard ? `✷ ${t.labels.anyWeapon}` : roll.weaponName}
                  {roll.input.trash ? " 👎" : ""}
                </span>
                <span className="r-sub">
                  {roll.typeLabel || ""}
                  {roll.lines.length > 1 ? ` · ${roll.lines.length} ${t.list.lines}` : ""}
                  {roll.input.tags.length ? ` · ${roll.input.tags.join(",")}` : ""}
                </span>
              </span>
              <button className="x" title={t.list.delete} onClick={() => removeRoll(roll.id)}>✕</button>
            </div>
          );
        })}
      </div>
      {rolls.length > 0 && (
        <div className="rail-foot">
          <button className="btn ghost sm" style={{ width: "100%" }} onClick={clear}>
            {t.list.clearAll} ({rolls.length})
          </button>
        </div>
      )}
    </aside>
  );
}