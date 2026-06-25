import { useEffect, useState } from "react";
import { api } from "./api";
import type { Status, WeaponSummary } from "./api";
import { Builder } from "./components/Builder";
import { WeaponSearch } from "./components/WeaponSearch";
import { ListRail } from "./components/ListRail";
import { MetaDashboard } from "./components/MetaDashboard";
import { ScoringProfileEditor } from "./components/ScoringProfileEditor";
import { InventoryCleanup } from "./components/InventoryCleanup";

const TABS: Array<[string, string]> = [
  ["builder", "빌더"],
  ["scoring", "점수 기준"],
  ["vault", "내 창고"],
  ["meta", "메타 대시보드"],
];

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [tab, setTab] = useState<"builder" | "meta" | "scoring" | "vault">("builder");
  const [menuOpen, setMenuOpen] = useState(false);
  const [picked, setPicked] = useState<WeaponSummary | null>(null);  // 헤더 검색 → 빌더 뷰어

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  // ESC 로 드로어 닫기
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const isSeed = status?.data_source === "seed";
  const activeLabel = TABS.find(([k]) => k === tab)?.[1] ?? "";

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="logo">
          <span className="gem" />
          <span className="wordmark">
            DIM <span className="accent">위시리스트</span> 허브
          </span>
        </div>
        {tab === "builder" && (
          <WeaponSearch activeHash={picked?.item_hash} onSelect={setPicked} />
        )}
        <div className="header-right">
          <span className="header-active-tab">{activeLabel}</span>
          <button
            className={`hamburger ${menuOpen ? "open" : ""}`}
            aria-label={menuOpen ? "메뉴 닫기" : "메뉴 열기"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
          >
            <span /><span /><span />
          </button>
        </div>
      </header>

      {/* 우측 드로어 (오프캔버스) + 딤 스크림 */}
      <div className={`drawer-scrim ${menuOpen ? "open" : ""}`} onClick={() => setMenuOpen(false)} />
      <aside className={`drawer ${menuOpen ? "open" : ""}`} aria-hidden={!menuOpen}>
        <div className="drawer-title">메뉴</div>
        <nav className="drawer-nav">
          {TABS.map(([k, label]) => (
            <button
              key={k}
              className={`drawer-tab ${tab === k ? "active" : ""}`}
              onClick={() => { setTab(k as typeof tab); setMenuOpen(false); }}
            >
              {label}
            </button>
          ))}
        </nav>
        {status && (
          <div className="drawer-status" title={status.note ?? ""}>
            <span className={`status-dot ${isSeed ? "seed" : ""}`} />
            {isSeed ? "샘플 데이터" : "매니페스트"} · 무기 {status.weapons}
          </div>
        )}
      </aside>

      {tab === "builder" && (
        <div className="builder-shell">
          <ListRail />
          <Builder picked={picked} />
        </div>
      )}
      {tab === "scoring" && <div className="page"><ScoringProfileEditor /></div>}
      {tab === "vault" && <div className="page"><InventoryCleanup /></div>}
      {tab === "meta" && <div className="page"><MetaDashboard /></div>}
    </div>
  );
}
