import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { en, type Messages } from "./en";

export type LanguageCode = "en";

export const LANGUAGES: Array<{ code: LanguageCode; label: string }> = [
  { code: "en", label: en.language.english },
];

const RESOURCES: Record<LanguageCode, Messages> = {
  en,
};

interface LanguageContextValue {
  language: LanguageCode;
  setLanguage: (lang: LanguageCode) => void;
  t: Messages;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);
const STORAGE_KEY = "dimhub.language";

function initialLanguage(): LanguageCode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en") return saved;
  } catch { /* ignore */ }
  return "en";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<LanguageCode>(initialLanguage);

  const setLanguage = (lang: LanguageCode) => {
    setLanguageState(lang);
    try { localStorage.setItem(STORAGE_KEY, lang); } catch { /* ignore */ }
  };

  const value = useMemo<LanguageContextValue>(
    () => ({ language, setLanguage, t: RESOURCES[language] }),
    [language],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within LanguageProvider");
  return ctx;
}

export function displayName(
  item: { name?: string | null; name_en?: string | null } | null | undefined,
  language: LanguageCode,
): string {
  if (!item) return "";
  if (language === "en") return item.name_en || item.name || "";
  return item.name || item.name_en || "";
}

export function formatTemplate(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));
}
export function weaponTypeLabel(
  subtype: number | null | undefined,
  t: Messages,
  fallback?: string | null,
): string {
  if (subtype == null) return fallback || t.labels.weapon;
  return t.game.weaponType[subtype as keyof typeof t.game.weaponType] || fallback || String(subtype);
}

export function damageLabel(
  damageType: string | null | undefined,
  t: Messages,
  fallback?: string | null,
): string {
  if (!damageType) return fallback || "";
  return t.game.damage[damageType as keyof typeof t.game.damage] || fallback || damageType;
}

export function tierLabel(
  tier: number | null | undefined,
  t: Messages,
  fallback?: string | null,
): string {
  if (tier == null) return fallback || "";
  return t.game.tier[tier as keyof typeof t.game.tier] || fallback || String(tier);
}

export function slotLabel(
  slot: string | null | undefined,
  t: Messages,
  fallback?: string | null,
): string {
  if (!slot) return fallback || "";
  return t.game.slot[slot as keyof typeof t.game.slot] || fallback || slot;
}

export function ammoLabel(
  ammo: number | string | null | undefined,
  t: Messages,
  fallback?: string | null,
): string {
  if (ammo == null || ammo === "") return fallback || "";
  const key = Number(ammo) as keyof typeof t.game.ammo;
  return t.game.ammo[key] || fallback || String(ammo);
}

export function columnKindLabel(kind: string | null | undefined, t: Messages, fallback?: string | null): string {
  if (!kind) return fallback || "";
  return t.scoring.columns[kind as keyof typeof t.scoring.columns] || fallback || kind;
}