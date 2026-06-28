// 백엔드 API 클라이언트 + 타입. 기본 베이스는 Vite 프록시('/api' -> :8000).
import type { SavedRoll } from "./store";

const BASE = (import.meta.env.VITE_API_BASE as string) ?? "/api";

// 로그인 시작용 절대 경로(브라우저 네비게이션 — fetch 아님).
export const LOGIN_URL = `${BASE}/auth/bungie/login`;

export interface AuthMe {
  connected: boolean;
  membership_id?: string | null;
  name?: string | null;
}

export interface UserState {
  rolls: SavedRoll[];
  title: string;
  description: string;
  activeProfileId: string | null;
}

export interface Perk {
  plug_hash: number;
  name: string;
  name_en?: string | null;
  description?: string | null;
  description_en?: string | null;
  icon?: string | null;
  plug_category?: string | null;
  currently_can_roll: boolean;
  is_curated: boolean;
  is_enhanced: boolean;
  popularity: number;
  stats?: Record<string, number> | null;  // 스탯 델타
  weight?: number | null;                  // 활성 프로필 가중치 (Phase 2)
}

export interface Column {
  index: number;
  kind: string; // barrel | magazine | trait | origin | intrinsic
  label: string;
  perks: Perk[];
}

export interface WeaponSummary {
  item_hash: number;
  name: string;
  name_en?: string | null;
  icon?: string | null;
  watermark?: string | null;
  tier?: number | null;
  tier_label?: string | null;
  weapon_subtype?: number | null;
  type_label?: string | null;
  slot?: string | null;
  default_damage_type?: string | null;
  damage_label?: string | null;
  stats?: Record<string, number> | null;
  score?: number | null;
  classification?: string | null;
  variant_count?: number;        // 이 시즌의 무기 수(일반+홀로포일)
  has_holofoil?: boolean;        // 이 시즌에 홀로포일 존재
  has_adept?: boolean;           // 이 시즌에 에이뎁트 존재
  is_holofoil?: boolean;         // 이 무기 자체가 홀로포일
  season_count?: number;         // 이 무기의 총 시즌(복각) 수
  season_number?: number | null; // 출시 시즌 번호 (예: 5)
  season_name?: string | null;   // 시즌명 (ko, 예: 대장간 시즌)
  season_name_en?: string | null; // 시즌명 (en) — 영어 모드 표시용
}

export interface WeaponDetail extends WeaponSummary {
  columns: Column[];
}

export interface PerkLite {
  plug_hash: number;
  name: string;
  name_en?: string | null;
  icon?: string | null;
  plug_category?: string | null;
}

export interface StatDef {
  stat_hash: number;
  key: string;
  name: string;
  name_en?: string | null;
}

export interface SynergyBonus {
  perks: number[];
  bonus: number;
  note?: string;
}

export interface ScoringProfile {
  id?: string | null;
  name: string;
  description?: string;
  tags?: string[];
  stat_weights: Record<string, number>;
  perk_weights: Record<string, number>;
  context_weights?: Record<string, Record<string, number>>;        // "type:9" → {plug: w}
  synergy_bonuses: SynergyBonus[];
  context_synergies?: Record<string, SynergyBonus[]>;              // "type:24" → combos
  use_wishlist_weights: boolean;
  blend: Record<string, number>;
  scope_blend?: Record<string, number>;     // 무기/프레임/종류 비중
  column_weights?: Record<string, number>;  // 총열/탄창/특성/기원 비중
  thresholds: Record<string, number>;
  updated_at?: string | null;
}

export interface DeriveContext {
  scope: string;
  label: string;
  kind: string; // type | frame | weapon
  weights: Array<{ plug_hash: number; weight: number; name?: string | null }>;
  combos: Array<{ perks: Array<{ plug_hash: number; name?: string | null }>; bonus: number }>;
}

export interface DeriveResult {
  rolls_parsed: number;
  context_weights: Record<string, Record<string, number>>;
  context_synergies: Record<string, SynergyBonus[]>;
  contexts: DeriveContext[];
}

export interface ImportedRoll {
  input: RollInput;
  weapon_name: string;
  weapon_name_en?: string | null;
  perk_labels: string[];
  perk_labels_en?: string[];
  lines: string[];
  type_label?: string | null;
  damage_type?: string | null;
  tier?: number | null;
}

export interface ImportResult {
  title?: string | null;
  description?: string | null;
  rolls: ImportedRoll[];
  imported: number;
  unknown_weapons: number;
  skipped_lines: number;
  wildcard: number;
}

export interface ScoreResult {
  score: number | null;          // null = 점수 기준 없음(위시리스트/프로필 가중치 미존재)
  classification: string | null; // god | viable | trash | null
  breakdown: Record<string, number | null>;
  stats: Record<string, number>;
  coverage?: number | null;      // 점수 신뢰도(기여 스코프 비중 합). 미등록 무기<1.0
  max_possible?: number | null;  // 동적 만점(무기 채점가능 열 비중 합)
}

export interface PerkWeights {
  weights: Record<string, number>; // plug_hash(문자열) → 가중치 (대략 -1..1)
  has_signal: boolean;             // false = 이 무기 관련 위시리스트/프로필 기준 없음
  scale: number;                   // 배지 점수 = weight * scale (desirability, ≈50)
  max_possible: number;            // 동적 만점(열 비중 합)
  coverage: number;                // 점수 신뢰도(스코프 비중 합). 미등록 무기<1.0
  column_weights: Record<string, number>; // 열종류 → 비중(특성/총열/탄창/기원)
  kinds: Record<string, string>;   // plug_hash → 열종류(barrel|magazine|trait|origin|intrinsic)
}

export interface WeaponFilters {
  subtypes?: number[];   // 무기 종류(OR)
  tiers?: number[];      // 등급(OR)
  damages?: string[];    // 속성(OR)
  slots?: string[];      // 슬롯(OR)
  ammo?: number[];       // 탄약(OR)
  frames?: string[];     // 프레임(OR)
  origins?: string[];    // 기원 특성 이름(OR)
  seasons?: number[];    // 시즌 번호(OR)
  perks?: number[];      // 정확 plug_hash(AND)
  perkExclude?: number[]; // 제외 plug_hash
  perkNames?: string[];  // 퍽 이름(각 OR, 이름 간 AND)
  statMin?: Record<string, number>; // {handling: 50}
  statMax?: Record<string, number>; // {recoil: 20}
  query?: string;        // DIM식 텍스트 쿼리(Phase B)
}

export interface FacetOption {
  value: number | string;
  label: string;        // ko 라벨(또는 매핑 없는 동적 값)
  label_en?: string | null; // en 라벨 — 프레임/기원/시즌 등 동적 매니페스트 값의 영어 표기
  count: number;
}

export interface FilterFacets {
  elements: FacetOption[];  // 속성
  types: FacetOption[];     // 종류
  tiers: FacetOption[];     // 등급
  slots: FacetOption[];     // 슬롯
  ammo: FacetOption[];      // 탄약
  frames: FacetOption[];    // 프레임(아키타입)
  origins: FacetOption[];   // 기원 특성
  seasons: FacetOption[];   // 시즌(복각)
}

export interface SearchHelp {
  operators: string[];
  keywords: Array<{ token: string; 예: string }>;
  examples: string[];
}

export interface Status {
  data_source: string;
  manifest_version: string;
  weapons: number;
  bungie_key_configured: boolean;
  note?: string | null;
}

export interface RollInput {
  weapon_hash: number;
  columns: Record<string, number[]>;
  wildcard: boolean;
  trash: boolean;
  notes: string;
  tags: string[];
  comment: string;
}

export interface CompileResult {
  lines: string[];
  line_count: number;
}

export interface ExportResult {
  filename: string;
  content: string;
  line_count: number;
  roll_count: number;
  data_source: string;
  warning?: string | null;
}

export interface TopWeapon {
  item_hash: number;
  name: string;
  name_en?: string | null;
  icon?: string | null;
  weapon_subtype?: number | null;
  type_label?: string | null;
  default_damage_type?: string | null;
  damage_label?: string | null;
  tier?: number | null;
  tier_label?: string | null;
  total: number;
}

// credentials: "include" — 세션 쿠키(dimhub_session)를 항상 동봉(개발 교차출처 대비).
async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path, { credentials: "include" });
  if (!r.ok) {
    // 백엔드 detail(예: 검색 쿼리 오류 메시지)을 우선 노출
    let detail = "";
    try { detail = (await r.json())?.detail ?? ""; } catch { /* ignore */ }
    throw new Error(detail || `GET ${path} -> ${r.status}`);
  }
  return r.json();
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method,
    credentials: "include",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json())?.detail ?? ""; } catch { /* ignore */ }
    throw new Error(detail || `${method} ${path} -> ${r.status}`);
  }
  return r.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return send<T>("POST", path, body);
}

const searchHelpers = {
  searchParams: (q: string, filters: WeaponFilters = {}) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (filters.subtypes?.length) p.set("subtypes", filters.subtypes.join(","));
    if (filters.tiers?.length) p.set("tiers", filters.tiers.join(","));
    if (filters.damages?.length) p.set("damages", filters.damages.join(","));
    if (filters.slots?.length) p.set("slots", filters.slots.join(","));
    if (filters.ammo?.length) p.set("ammo", filters.ammo.join(","));
    if (filters.frames?.length) p.set("frames", filters.frames.join(","));
    if (filters.origins?.length) p.set("origins", filters.origins.join(","));
    if (filters.seasons?.length) p.set("seasons", filters.seasons.join(","));
    if (filters.perks?.length) p.set("perks", filters.perks.join(","));
    if (filters.perkExclude?.length) p.set("perk_exclude", filters.perkExclude.join(","));
    for (const nm of filters.perkNames ?? []) p.append("perkname", nm);
    for (const [k, v] of Object.entries(filters.statMin ?? {})) p.append("stat_min", `${k}:${v}`);
    for (const [k, v] of Object.entries(filters.statMax ?? {})) p.append("stat_max", `${k}:${v}`);
    if (filters.query?.trim()) p.set("query", filters.query.trim());
    return p;
  },
};

export const api = {
  status: () => get<Status>("/status"),
  searchWeapons: (q: string, filters: WeaponFilters = {}) => {
    const p = searchHelpers.searchParams(q, filters);
    p.set("limit", "60");
    return get<WeaponSummary[]>(`/weapons?${p.toString()}`);
  },
  countWeapons: (q: string, filters: WeaponFilters = {}) =>
    get<{ count: number }>(`/weapons/count?${searchHelpers.searchParams(q, filters).toString()}`),
  // 컨텍스트 인지 패싯 — 현재 검색/필터 기준으로 가용 값+갯수
  filters: (q = "", filters: WeaponFilters = {}) =>
    get<FilterFacets>(`/filters?${searchHelpers.searchParams(q, filters).toString()}`),
  searchHelp: (lang: string = "ko") => get<SearchHelp>(`/search/help?lang=${lang}`),
  weapon: (hash: number) => get<WeaponDetail>(`/weapons/${hash}`),
  searchPerks: (q: string) => get<PerkLite[]>(`/perks?q=${encodeURIComponent(q)}`),
  statDefs: () => get<StatDef[]>("/stat-defs"),
  compile: (roll: RollInput) => post<CompileResult>("/compile", roll),
  exportList: (payload: { title?: string; description?: string; rolls: RollInput[] }) =>
    post<ExportResult>("/export", payload),
  importWishlist: (text: string) => post<ImportResult>("/import-wishlist", { text }),
  topWeapons: (limit = 20) => get<TopWeapon[]>(`/meta/top-weapons?limit=${limit}`),

  // --- v2 점수화 ---
  listProfiles: () => get<ScoringProfile[]>("/scoring-profiles"),
  getProfile: (id: string) => get<ScoringProfile>(`/scoring-profiles/${id}`),
  saveProfile: (p: ScoringProfile) => post<ScoringProfile>("/scoring-profiles", p),
  deleteProfile: (id: string) => send<{ deleted: string }>("DELETE", `/scoring-profiles/${id}`),

  // --- 인증 / 사용자 상태 (멀티유저) ---
  me: () => get<AuthMe>("/auth/me"),
  logout: () => post<{ ok: boolean }>("/auth/logout", {}),
  loadState: () => get<UserState>("/me/state"),
  saveState: (s: UserState) => send<{ ok: boolean }>("PUT", "/me/state", s),
  score: (body: {
    weapon_hash: number;
    perks: number[];
    profile?: ScoringProfile | null;
    profile_id?: string | null;
    wishlist_rolls?: RollInput[];
  }) => post<ScoreResult>("/score", body),
  deriveWeights: (body: { rolls?: RollInput[]; text?: string }) =>
    post<DeriveResult>("/scoring/derive-weights", body),
  perkWeights: (body: {
    weapon_hash: number;
    profile?: ScoringProfile | null;
    profile_id?: string | null;
    wishlist_rolls?: RollInput[];
  }) => post<PerkWeights>("/score/perk-weights", { perks: [], ...body }),
};

export interface InventoryStatus {
  connected: boolean;
  membership_id?: string | null;
  item_count: number;
  synced_at?: string | null;
  oauth_configured: boolean;
  login_url?: string | null;
}

export interface InvPerk {
  plug_hash: number;
  name?: string | null;
  name_en?: string | null;
  icon?: string | null;
  column_kind?: string | null;
  column_index?: number | null;
  equipped?: boolean;
  points?: number | null;     // 퍽 선호도 점수(없으면 미표시)
}

export interface CleanupItem {
  item_instance_id: string;
  item_hash: number;
  name: string;
  name_en?: string | null;
  icon?: string | null;
  weapon_subtype?: number | null;
  type_label?: string | null;
  default_damage_type?: string | null;
  damage_label?: string | null;
  tier?: number | null;
  power?: number | null;
  perks: InvPerk[];                 // 장착 롤(평면)
  perk_columns?: InvPerk[][];       // 열별 선택 가능 퍽(제작=다중)
  stats: Record<string, number>;
  score?: number | null;            // 현재 장착 롤 점수
  classification?: string | null;
  best_score?: number | null;       // 열별 최선 퍽 선택 시 최고 점수
  best_classification?: string | null;
}

export const inventoryApi = {
  status: () => get<InventoryStatus>("/me/status"),
  demo: () => post<InventoryStatus>("/me/demo-inventory", {}),
  sync: () => post<InventoryStatus>("/me/sync", {}),
  cleanup: (profile: ScoringProfile | null, wishlist_rolls: RollInput[]) =>
    post<CleanupItem[]>("/me/cleanup", { profile, wishlist_rolls }),
  weaponRolls: (weapon_hash: number, profile: ScoringProfile | null, wishlist_rolls: RollInput[]) =>
    post<CleanupItem[]>("/me/weapon-rolls", { weapon_hash, profile, wishlist_rolls }),
  exportTrashlist: (profile: ScoringProfile | null, wishlist_rolls: RollInput[]) =>
    post<{ filename: string; content: string; trash_count: number; line_count: number }>(
      "/me/export-trashlist", { profile, wishlist_rolls },
    ),
};

export const CLASS_LABEL: Record<string, string> = { god: "God roll", viable: "Viable", trash: "Cleanup" };
export const CLASS_COLOR: Record<string, string> = {
  god: "var(--primary)",
  viable: "var(--community)",
  trash: "var(--danger)",
};

// 퍽별 표시 점수(가중치 * scale) → 등급/색. 양수=좋음(앰버→초록→파랑), 음수=트래시(빨강), 0=중립.
export type PerkTier = "s" | "a" | "b" | "trash" | "neutral";
export function perkTier(points: number): PerkTier {
  if (points >= 35) return "s";       // 핵심 퍽
  if (points >= 15) return "a";       // 좋은 퍽
  if (points > 0) return "b";         // 약한 선호
  if (points < 0) return "trash";     // 트래시(감점)
  return "neutral";                   // 신호 없음
}
export const PERK_TIER_COLOR: Record<PerkTier, string> = {
  s: "var(--primary)",      // 앰버
  a: "var(--success)",      // 초록
  b: "var(--community)",    // 파랑
  trash: "var(--danger)",   // 빨강
  neutral: "var(--text-faint)",
};

export const ELEM_VAR: Record<string, string> = {
  Kinetic: "--elem-kinetic",
  Arc: "--elem-arc",
  Solar: "--elem-solar",
  Void: "--elem-void",
  Stasis: "--elem-stasis",
  Strand: "--elem-strand",
  Prismatic: "--elem-prismatic",
};

export const RARITY_VAR: Record<number, string> = {
  5: "--rarity-legendary",
  6: "--rarity-exotic",
};
