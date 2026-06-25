import { useRef, useState } from "react";
import { api, ELEM_VAR, RARITY_VAR } from "../api";
import type { ImportResult } from "../api";
import { useWishlist } from "../store";

// 좌측 "내 리스트" 레일 — 위시리스트에 추가된 롤 목록 + 외부 위시리스트 가져오기.
export function ListRail() {
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
      weaponName: ir.weapon_name,
      perkLabels: ir.perk_labels,
      lines: ir.lines,
      typeLabel: ir.type_label,
      damageType: ir.damage_type,
      tier: ir.tier,
    })));
    if (res.title) setTitle(res.title);
    if (res.description) setDescription(res.description);
    const extra = [
      res.unknown_weapons ? `미보유 무기 ${res.unknown_weapons}` : "",
      res.wildcard ? `와일드카드 ${res.wildcard}` : "",
      res.skipped_lines ? `실패 ${res.skipped_lines}줄` : "",
    ].filter(Boolean).join(" · ");
    setStatus(`가져옴 ${res.imported}개${extra ? ` (제외: ${extra})` : ""}`);
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    setStatus("가져오는 중…");
    try {
      const text = await f.text();
      const res = await api.importWishlist(text);
      if (res.imported === 0) {
        setStatus(`가져올 롤이 없습니다 (실패 ${res.skipped_lines}줄, 미보유 ${res.unknown_weapons})`);
        return;
      }
      const replace = rolls.length > 0
        ? window.confirm(`${res.imported}개 롤을 가져옵니다.\n확인=기존 리스트 비우고 교체 / 취소=기존에 추가`)
        : true;
      applyImport(res, replace);
    } catch (err) {
      setStatus(`가져오기 실패: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="list-rail">
      <div className="rail-head">
        <span className="rail-title">내 리스트</span>
        <button className="rail-add" title="외부 위시리스트(.txt) 가져오기" disabled={busy}
                onClick={() => fileRef.current?.click()}>⤓</button>
        <button className="rail-add" title="무기 추가" onClick={focusSearch}>+</button>
        <input ref={fileRef} type="file" accept=".txt,text/plain" hidden onChange={onFile} />
      </div>
      {status && <div className="rail-status">{status}</div>}
      <div className="rail-list">
        {rolls.length === 0 && (
          <div className="rail-empty">
            추가된 롤이 없습니다.<br />가운데에서 퍼크를 골라 추가하거나,<br />⤓ 로 외부 위시리스트(.txt)를 가져오세요.
          </div>
        )}
        {rolls.map((r) => {
          const elemVar = r.damageType ? ELEM_VAR[r.damageType] : undefined;
          const rarityVar = r.tier ? RARITY_VAR[r.tier] : undefined;
          const cls = r.input.wildcard ? "wild" : r.input.trash ? "trash" : "";
          return (
            <div key={r.id} className={`rail-item ${cls}`}>
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
                  {r.input.wildcard ? "✷ 아무 무기" : r.weaponName}
                  {r.input.trash ? " 👎" : ""}
                </span>
                <span className="r-sub">
                  {r.typeLabel || ""}
                  {r.lines.length > 1 ? ` · ${r.lines.length}줄` : ""}
                  {r.input.tags.length ? ` · ${r.input.tags.join(",")}` : ""}
                </span>
              </span>
              <button className="x" title="삭제" onClick={() => removeRoll(r.id)}>✕</button>
            </div>
          );
        })}
      </div>
      {rolls.length > 0 && (
        <div className="rail-foot">
          <button className="btn ghost sm" style={{ width: "100%" }} onClick={clear}>전체 비우기 ({rolls.length})</button>
        </div>
      )}
    </aside>
  );
}
