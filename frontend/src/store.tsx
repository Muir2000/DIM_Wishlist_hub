import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { RollInput, ScoringProfile } from "./api";

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
  const [rolls, setRolls] = useState<SavedRoll[]>([]);
  const [title, setTitle] = useState("My wishlist");
  const [description, setDescription] = useState("");
  const [activeProfile, setActiveProfile] = useState<ScoringProfile | null>(null);

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
