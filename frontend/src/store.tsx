import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import type { RollInput, ScoringProfile } from "./api";
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
  rolls: SavedRoll[];
  title: string;
  description: string;
  addRoll: (r: Omit<SavedRoll, "id">) => void;
  addRolls: (rs: Omit<SavedRoll, "id">[]) => void;
  removeRoll: (id: number) => void;
  clear: () => void;
  setTitle: (s: string) => void;
  setDescription: (s: string) => void;
  // v2 점수화
  activeProfile: ScoringProfile | null;
  setActiveProfile: (p: ScoringProfile | null) => void;
}

const Ctx = createContext<WishlistCtx | null>(null);

let _id = 1;

export function WishlistProvider({ children }: { children: ReactNode }) {
  const { loggedIn } = useAuth();
  const [rolls, setRolls] = useState<SavedRoll[]>([]);
  const [title, setTitle] = useState("My wishlist");
  const [description, setDescription] = useState("");
  const [activeProfile, setActiveProfile] = useState<ScoringProfile | null>(null);
  const hydrated = useRef(false);  // 서버 상태 로드 완료(이후에만 자동 저장)

  // 로그인 시 서버에 저장된 빌더 상태(롤·활성 프로필) 복원. 로그아웃 시 초기화.
  useEffect(() => {
    if (!loggedIn) {
      hydrated.current = false;
      setRolls([]); setTitle("My wishlist"); setDescription(""); setActiveProfile(null);
      return;
    }
    let cancelled = false;
    api.loadState().then(async (s) => {
      if (cancelled) return;
      const loaded = (s.rolls ?? []) as SavedRoll[];
      setRolls(loaded);
      _id = Math.max(_id, ...loaded.map((r) => r.id + 1), 1);
      setTitle(s.title || "My wishlist");
      setDescription(s.description || "");
      if (s.activeProfileId) {
        try { setActiveProfile(await api.getProfile(s.activeProfileId)); }
        catch { setActiveProfile(null); }
      } else {
        setActiveProfile(null);
      }
      if (!cancelled) hydrated.current = true;
    }).catch(() => { hydrated.current = true; });
    return () => { cancelled = true; };
  }, [loggedIn]);

  // 변경 시 디바운스 자동 저장(로그인 + 하이드레이션 후).
  useEffect(() => {
    if (!loggedIn || !hydrated.current) return;
    const h = window.setTimeout(() => {
      api.saveState({ rolls, title, description, activeProfileId: activeProfile?.id ?? null })
        .catch(() => {});
    }, 800);
    return () => window.clearTimeout(h);
  }, [loggedIn, rolls, title, description, activeProfile]);

  const addRoll = (r: Omit<SavedRoll, "id">) =>
    setRolls((prev) => [...prev, { ...r, id: _id++ }]);
  const addRolls = (rs: Omit<SavedRoll, "id">[]) =>
    setRolls((prev) => [...prev, ...rs.map((r) => ({ ...r, id: _id++ }))]);
  const removeRoll = (id: number) => setRolls((prev) => prev.filter((x) => x.id !== id));
  const clear = () => setRolls([]);

  const value = useMemo<WishlistCtx>(
    () => ({ rolls, title, description, addRoll, addRolls, removeRoll, clear, setTitle, setDescription,
             activeProfile, setActiveProfile }),
    [rolls, title, description, activeProfile],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWishlist(): WishlistCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useWishlist must be used within WishlistProvider");
  return c;
}
