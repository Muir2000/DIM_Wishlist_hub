import { useEffect, useState } from "react";
import { api } from "./api";
import type { Status, WeaponSummary } from "./api";
import { Builder } from "./components/Builder";
import { WeaponSearch } from "./components/WeaponSearch";
import { ListRail } from "./components/ListRail";
import { MetaDashboard } from "./components/MetaDashboard";
import { ScoringProfileEditor } from "./components/ScoringProfileEditor";
import { InventoryCleanup } from "./components/InventoryCleanup";
import { LANGUAGES, useLanguage, type LanguageCode } from "./i18n";
import { useAuth } from "./auth";

type TabKey = "builder" | "meta" | "scoring" | "vault";

const TABS: TabKey[] = ["builder", "scoring", "vault", "meta"];

export default function App() {
  const { language, setLanguage, t } = useLanguage();
  const { me, loggedIn, login, logout } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [tab, setTab] = useState<TabKey>("builder");
  const [menuOpen, setMenuOpen] = useState(false);
  const [picked, setPicked] = useState<WeaponSummary | null>(null);
  // 롤 불러오기: 무기 선택 + 적용할 퍽 선택(빌더가 소비). {hash, columns} 형태.
  const [pending, setPending] = useState<{ hash: number; columns: Record<string, number[]> } | null>(null);
  const loadRoll = (hash: number, columns: Record<string, number[]>, summary?: Partial<WeaponSummary>) => {
    setTab("builder");
    setPicked({ item_hash: hash, name: "", ...summary } as WeaponSummary);
    setPending({ hash, columns });
  };

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const isSeed = status?.data_source === "seed";
  const activeLabel = t.app.tabs[tab];

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="logo">
          <span className="gem" />
          <span className="wordmark">
            {t.app.titlePrefix} <span className="accent">{t.app.titleAccent}</span> {t.app.titleSuffix}
          </span>
        </div>
        {tab === "builder" && (
          <WeaponSearch activeHash={picked?.item_hash} onSelect={setPicked} />
        )}
        <div className="header-right">
          <span className="header-active-tab">{activeLabel}</span>
          <button
            className={`hamburger ${menuOpen ? "open" : ""}`}
            aria-label={menuOpen ? t.app.closeMenu : t.app.openMenu}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
          >
            <span /><span /><span />
          </button>
        </div>
      </header>

      <div className={`drawer-scrim ${menuOpen ? "open" : ""}`} onClick={() => setMenuOpen(false)} />
      <aside className={`drawer ${menuOpen ? "open" : ""}`} aria-hidden={!menuOpen}>
        <div className="drawer-title">{t.app.menu}</div>
        <nav className="drawer-nav">
          {TABS.map((key) => (
            <button
              key={key}
              className={`drawer-tab ${tab === key ? "active" : ""}`}
              onClick={() => { setTab(key); setMenuOpen(false); }}
            >
              {t.app.tabs[key]}
            </button>
          ))}
        </nav>

        <div className="drawer-settings">
          <div className="drawer-section-title">{t.app.settings}</div>
          <label className="drawer-setting" title={t.language.label}>
            <span>{t.language.label}</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as LanguageCode)}
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>{lang.label}</option>
              ))}
            </select>
          </label>

          <div className="drawer-setting account">
            <span>{t.app.account}</span>
            {loggedIn ? (
              <span className="account-actions">
                <span className="account-name">{me?.name ?? me?.membership_id}</span>
                <button className="btn ghost sm" onClick={() => { logout(); }}>{t.app.logout}</button>
              </span>
            ) : (
              <button className="btn primary sm" onClick={login}>{t.vault.login}</button>
            )}
          </div>
          {!loggedIn && <div className="drawer-login-hint">{t.app.loginHint}</div>}
        </div>

        {status && (
          <div className="drawer-status" title={status.note ?? ""}>
            <span className={`status-dot ${isSeed ? "seed" : ""}`} />
            {isSeed ? t.app.sampleData : t.app.manifest} · {status.weapons} {t.app.weapons}
          </div>
        )}
      </aside>

      {tab === "builder" && (
        <div className="builder-shell">
          <ListRail onLoadRoll={loadRoll} picked={picked} />
          <Builder picked={picked} pending={pending} clearPending={() => setPending(null)} onLoadRoll={loadRoll} />
        </div>
      )}
      {tab === "scoring" && <div className="page"><ScoringProfileEditor /></div>}
      {tab === "vault" && <div className="page"><InventoryCleanup /></div>}
      {tab === "meta" && <div className="page"><MetaDashboard /></div>}
    </div>
  );
}