import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import type { RollInput, ScoringProfile, SynergyBonus } from "./api";
import { useAuth } from "./auth";

export interface SavedRoll {
  id: number;
  input: RollInput;
  weaponName: string;
  perkLabels: string[];
  lines: string[];
  typeLabel?: string | null;
  damageType?: string | null;
  tier?: number | null;
}

interface WishlistCtx {
  rolls: SavedRoll[];                 // 선택된 프로필들의 롤 합집합 (읽기)
  title: string;
  description: string;
  addRoll: (r: Omit<SavedRoll, "id">) => void;
  addRolls: (rs: Omit<SavedRoll, "id">[]) => void;
  removeRoll: (id: number) => void;
  clear: () => void;
  setTitle: (s: string) => void;
  setDescription: (s: string) => void;
  // 점수 프로필 (롤은 프로필에 보관)
  profiles: ScoringProfile[];                  // 저장된 전체 프로필(롤 포함)
  selectedIds: string[];                       // 내 리스트에 합칠 프로필들
  primaryId: string | null;                    // 가중치/편집 대상
  setSelection: (ids: string[], primary?: string | null) => void;
  refreshProfiles: () => Promise<void>;
  upsertProfile: (p: ScoringProfile) => Promise<ScoringProfile | null>;  // 가중치 저장(롤 보존)
  activeProfile: ScoringProfile | null;        // 편집/표시용(primary)
  scoringProfile: ScoringProfile | null;       // 점수 계산용(선택 프로필 병합)
  setActiveProfile: (p: ScoringProfile | null) => void;  // 단일 활성(호환)
}

const Ctx = createContext<WishlistCtx | null>(null);

let _id = 1;
const reid = (rs: SavedRoll[] = []): SavedRoll[] => rs.map((r) => ({ ...r, id: _id++ }));

function avgDict(dicts: Array<Record<string, number> | undefined>): Record<string, number> {
  const sum: Record<string, number> = {}, cnt: Record<string, number> = {};
  for (const d of dicts) for (const [k, v] of Object.entries(d ?? {})) {
    sum[k] = (sum[k] ?? 0) + v; cnt[k] = (cnt[k] ?? 0) + 1;
  }
  const out: Record<string, number> = {};
  for (const k of Object.keys(sum)) out[k] = sum[k] / cnt[k];
  return out;
}

// 선택된 여러 프로필을 점수용 1개로 결합(가중치 합집합 max, blend 평균). 1개면 그대로.
function mergeProfiles(profs: ScoringProfile[], primary: ScoringProfile | null): ScoringProfile | null {
  if (profs.length === 0) return primary;
  if (profs.length === 1) return profs[0];
  const base = primary ?? profs[0];
  const maxMerge = (key: "stat_weights" | "perk_weights"): Record<string, number> => {
    const out: Record<string, number> = {};
    for (const p of profs) for (const [k, v] of Object.entries(p[key] ?? {})) {
      out[k] = k in out ? Math.max(out[k], v) : v;
    }
    return out;
  };
  const ctxW: Record<string, Record<string, number>> = {};
  for (const p of profs) for (const [sc, m] of Object.entries(p.context_weights ?? {})) {
    ctxW[sc] = ctxW[sc] ?? {};
    for (const [plug, v] of Object.entries(m)) ctxW[sc][plug] = plug in ctxW[sc] ? Math.max(ctxW[sc][plug], v) : v;
  }
  const ctxS: Record<string, SynergyBonus[]> = {};
  for (const p of profs) for (const [sc, arr] of Object.entries(p.context_synergies ?? {})) {
    ctxS[sc] = [...(ctxS[sc] ?? []), ...arr];
  }
  return {
    ...base,
    name: `(${profs.length})`,
    stat_weights: maxMerge("stat_weights"),
    perk_weights: maxMerge("perk_weights"),
    context_weights: ctxW,
    synergy_bonuses: profs.flatMap((p) => p.synergy_bonuses ?? []),
    context_synergies: ctxS,
    use_wishlist_weights: profs.some((p) => p.use_wishlist_weights),
    blend: avgDict(profs.map((p) => p.blend)),
    scope_blend: avgDict(profs.map((p) => p.scope_blend)),
    column_weights: avgDict(profs.map((p) => p.column_weights)),
    thresholds: base.thresholds,
    rolls: [],
  };
}

function defaultProfile(name: string, rolls: SavedRoll[]): ScoringProfile {
  return {
    id: null, name, description: "", tags: [],
    stat_weights: {}, perk_weights: {}, context_weights: {},
    synergy_bonuses: [], context_synergies: {}, use_wishlist_weights: true,
    blend: { stat: 1, perk: 1, synergy: 1 },
    scope_blend: { weapon: 0.6, frame: 0.25, type: 0.15 },
    column_weights: { trait: 1.0, barrel: 0.35, magazine: 0.35, origin: 0.2, intrinsic: 0.0 },
    thresholds: { god: 75, viable: 40 },
    rolls,
  };
}

export function WishlistProvider({ children }: { children: ReactNode }) {
  const { loggedIn } = useAuth();
  const [profiles, setProfiles] = useState<ScoringProfile[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [primaryId, setPrimaryId] = useState<string | null>(null);
  const [title, setTitle] = useState("My wishlist");
  const [description, setDescription] = useState("");
  const hydrated = useRef(false);

  const activeProfile = profiles.find((p) => p.id === primaryId) ?? null;
  const rolls = useMemo<SavedRoll[]>(() => {
    const out: SavedRoll[] = [];
    for (const p of profiles) {
      if (p.id && selectedIds.includes(p.id)) out.push(...((p.rolls as SavedRoll[]) ?? []));
    }
    return out;
  }, [profiles, selectedIds]);
  // 점수용: 선택된 프로필들을 1개로 병합(1개면 그대로). primary가 가중치 기준.
  const scoringProfile = useMemo<ScoringProfile | null>(() => {
    const sel = profiles.filter((p) => p.id && selectedIds.includes(p.id));
    return mergeProfiles(sel, activeProfile);
  }, [profiles, selectedIds, primaryId]);

  // 로그인 시: 프로필 목록 + 상태(선택/primary) 로드. 레거시 user_state.rolls 마이그레이션.
  useEffect(() => {
    if (!loggedIn) {
      hydrated.current = false;
      setProfiles([]); setSelectedIds([]); setPrimaryId(null);
      setTitle("My wishlist"); setDescription("");
      return;
    }
    let cancelled = false;
    (async () => {
      const [profsRaw, state] = await Promise.all([
        api.listProfiles().catch(() => [] as ScoringProfile[]),
        api.loadState().catch(() => null),
      ]);
      if (cancelled) return;
      let list = profsRaw.map((p) => ({ ...p, rolls: reid((p.rolls as SavedRoll[]) ?? []) }));

      // 마이그레이션: 레거시 단일 위시리스트(user_state.rolls) → 프로필로 이관(1회).
      // 로그인 사용자는 항상 최소 1개 프로필 보장(없으면 기본 생성).
      const legacy = reid(((state?.rolls as SavedRoll[]) ?? []));
      let primary = state?.primaryProfileId ?? state?.activeProfileId ?? null;
      if (list.length === 0) {
        const created = await api.saveProfile(defaultProfile("기본 프로필", legacy)).catch(() => null);
        if (created) { list = [{ ...created, rolls: reid((created.rolls as SavedRoll[]) ?? legacy) }]; primary = created.id ?? null; }
      } else if (legacy.length) {
        const prim = list.find((p) => p.id === (primary ?? list[0].id));
        if (prim && (!prim.rolls || prim.rolls.length === 0)) {
          const merged = { ...prim, rolls: legacy };
          await api.saveProfile(merged).catch(() => {});
          list = list.map((p) => (p.id === prim.id ? merged : p));
          primary = prim.id ?? null;
        }
      }
      if (!primary && list.length) primary = list[0].id ?? null;
      const sel = state?.activeProfileIds?.length
        ? state.activeProfileIds.filter((id) => list.some((p) => p.id === id))
        : (primary ? [primary] : []);

      setProfiles(list);
      setPrimaryId(primary);
      setSelectedIds(sel.length ? sel : (primary ? [primary] : []));
      setTitle(state?.title || "My wishlist");
      setDescription(state?.description || "");
      hydrated.current = true;
    })().catch(() => { hydrated.current = true; });
    return () => { cancelled = true; };
  }, [loggedIn]);

  // user_state 영속(선택/primary/제목만 — 롤은 프로필에 저장됨).
  useEffect(() => {
    if (!loggedIn || !hydrated.current) return;
    const h = window.setTimeout(() => {
      api.saveState({
        rolls: [], title, description,
        activeProfileId: primaryId, primaryProfileId: primaryId, activeProfileIds: selectedIds,
      }).catch(() => {});
    }, 800);
    return () => window.clearTimeout(h);
  }, [loggedIn, title, description, primaryId, selectedIds]);

  // 프로필 저장 + 로컬 상태 갱신.
  function persist(prof: ScoringProfile) {
    setProfiles((prev) => prev.map((p) => (p.id === prof.id ? prof : p)));
    api.saveProfile(prof).catch(() => {});
  }
  // primary 프로필의 롤을 편집.
  function editPrimaryRolls(fn: (cur: SavedRoll[]) => SavedRoll[]) {
    if (!activeProfile) return;  // 활성 프로필 필요
    persist({ ...activeProfile, rolls: fn((activeProfile.rolls as SavedRoll[]) ?? []) });
  }
  const addRoll = (r: Omit<SavedRoll, "id">) => editPrimaryRolls((cur) => [...cur, { ...r, id: _id++ }]);
  const addRolls = (rs: Omit<SavedRoll, "id">[]) =>
    editPrimaryRolls((cur) => [...cur, ...rs.map((r) => ({ ...r, id: _id++ }))]);
  const clear = () => editPrimaryRolls(() => []);
  // 합집합 표시이므로 롤이 속한 프로필을 찾아 제거.
  const removeRoll = (id: number) => {
    const owner = profiles.find((p) => ((p.rolls as SavedRoll[]) ?? []).some((r) => r.id === id));
    if (!owner) return;
    persist({ ...owner, rolls: ((owner.rolls as SavedRoll[]) ?? []).filter((r) => r.id !== id) });
  };

  const setSelection = (ids: string[], primary?: string | null) => {
    setSelectedIds(ids);
    if (primary !== undefined) setPrimaryId(primary);
    else if (!ids.includes(primaryId ?? "")) setPrimaryId(ids[0] ?? null);
  };
  const setActiveProfile = (p: ScoringProfile | null) => {
    if (!p || !p.id) { setSelectedIds([]); setPrimaryId(null); return; }
    setProfiles((prev) => (prev.some((x) => x.id === p.id) ? prev.map((x) => (x.id === p.id ? p : x)) : [...prev, p]));
    setSelectedIds([p.id]);
    setPrimaryId(p.id);
  };
  const refreshProfiles = async () => {
    const list = await api.listProfiles().catch(() => null);
    if (list) setProfiles(list.map((p) => ({ ...p, rolls: reid((p.rolls as SavedRoll[]) ?? []) })));
  };
  // 가중치 등 저장 — 해당 프로필의 현재 롤을 보존(빌더에서 추가한 롤 클로버 방지).
  const upsertProfile = async (p: ScoringProfile): Promise<ScoringProfile | null> => {
    const existing = profiles.find((x) => x.id === p.id);
    const merged = { ...p, rolls: p.rolls ?? (existing?.rolls as SavedRoll[]) ?? [] };
    const saved = await api.saveProfile(merged).catch(() => null);
    if (saved) {
      const withRolls = { ...saved, rolls: reid((saved.rolls as SavedRoll[]) ?? merged.rolls) };
      setProfiles((prev) => (prev.some((x) => x.id === withRolls.id) ? prev.map((x) => (x.id === withRolls.id ? withRolls : x)) : [...prev, withRolls]));
      return withRolls;
    }
    return null;
  };

  const value = useMemo<WishlistCtx>(
    () => ({
      rolls, title, description, addRoll, addRolls, removeRoll, clear, setTitle, setDescription,
      profiles, selectedIds, primaryId, setSelection, refreshProfiles, upsertProfile,
      activeProfile, scoringProfile, setActiveProfile,
    }),
    [rolls, title, description, profiles, selectedIds, primaryId, activeProfile, scoringProfile],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWishlist(): WishlistCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useWishlist must be used within WishlistProvider");
  return c;
}
