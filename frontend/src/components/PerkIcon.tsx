import type { Perk } from "../api";

// In-game approximation: barrels/magazines use rounded squares; traits/origins/intrinsics use circles.
export function PerkIcon({ perk, kind }: { perk: Perk; kind: string }) {
  const shape = kind === "barrel" || kind === "magazine" ? "square" : "circle";
  const label = perk.name_en || perk.name;
  return (
    <div className={`perk-icon ${shape}`} title={label}>
      {perk.icon ? <img src={perk.icon} alt="" loading="lazy" /> : (label?.[0] ?? "?")}
    </div>
  );
}