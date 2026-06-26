import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { en, type Messages } from "./en";
import { ko } from "./ko";

export type LanguageCode = "en" | "ko";

// 각 언어는 자기 언어 표기로 노출(활성 언어와 무관).
export const LANGUAGES: Array<{ code: LanguageCode; label: string }> = [
  { code: "ko", label: "한국어" },
  { code: "en", label: "English" },
];

const RESOURCES: Record<LanguageCode, Messages> = {
  en,
  ko,
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
    if (saved === "en" || saved === "ko") return saved;
  } catch { /* ignore */ }
  // 저장값이 없으면 브라우저 언어로 추정(영어권만 en, 그 외 기본 ko).
  try {
    if (navigator.language && navigator.language.toLowerCase().startsWith("en")) return "en";
  } catch { /* ignore */ }
  return "ko";
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

// 매니페스트 시즌명: 언어에 맞춰 season_name_en / season_name 중 선택(폴백 포함).
export function seasonName(
  item: { season_name?: string | null; season_name_en?: string | null } | null | undefined,
  language: LanguageCode,
): string {
  if (!item) return "";
  if (language === "en") return item.season_name_en || item.season_name || "";
  return item.season_name || item.season_name_en || "";
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