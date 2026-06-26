import { useEffect, useState } from "react";
import { api, ELEM_VAR } from "../api";
import type { TopWeapon } from "../api";
import { damageLabel, displayName, useLanguage, weaponTypeLabel } from "../i18n";

export function MetaDashboard() {
  const { language, t } = useLanguage();
  const [rows, setRows] = useState<TopWeapon[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.topWeapons(20).then(setRows).catch((e) => setErr(String(e)));
  }, []);

  const max = Math.max(1, ...rows.map((row) => row.total));

  return (
    <div className="page-narrow">
      <h1 style={{ fontSize: 32, textTransform: "uppercase", margin: "0 0 6px" }}>{t.meta.title}</h1>
      <p style={{ color: "var(--text-muted)", fontSize: 14, margin: "0 0 24px" }}>
        {t.meta.subtitle}
      </p>

      <div className="panel" style={{ padding: 0 }}>
        <div className="panel-title" style={{ padding: "14px 16px 0", margin: 0 }}>{t.meta.topWeapons}</div>
        {err && <div className="empty">{t.meta.loadFailed}: {err}</div>}
        {!err && rows.length === 0 && <div className="empty">{t.meta.empty}</div>}
        {rows.map((row, index) => {
          const elemVar = row.default_damage_type ? `var(${ELEM_VAR[row.default_damage_type] ?? ""})` : undefined;
          return (
            <div className="meta-row" key={row.item_hash}>
              <span className="rank">{index + 1}</span>
              <span className="elem-stripe" style={{ ["--elem-color" as any]: elemVar }} />
              <span style={{ minWidth: 150 }}>
                <span style={{ display: "block", fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em" }}>
                  {displayName(row, language)}
                </span>
                <span style={{ display: "block", fontSize: 11, color: "var(--text-faint)" }}>
                  {weaponTypeLabel(row.weapon_subtype, t, row.type_label)}{row.default_damage_type ? ` · ${damageLabel(row.default_damage_type, t, row.damage_label)}` : ""}
                </span>
              </span>
              <div className="meta-bar-wrap">
                <div className="meta-bar"><span style={{ width: `${Math.round((row.total / max) * 100)}%` }} /></div>
              </div>
              <span className="meta-total">{row.total.toLocaleString()}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}