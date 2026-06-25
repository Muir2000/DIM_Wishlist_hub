import type { Perk } from "../api";

// 인게임 모사: 배럴/탄창 = 둥근 사각, 특성/기원/고유 = 원형.
export function PerkIcon({ perk, kind }: { perk: Perk; kind: string }) {
  const shape = kind === "barrel" || kind === "magazine" ? "square" : "circle";
  return (
    <div className={`perk-icon ${shape}`} title={perk.name_en ?? perk.name}>
      {perk.icon ? <img src={perk.icon} alt="" loading="lazy" /> : (perk.name?.[0] ?? "?")}
    </div>
  );
}
