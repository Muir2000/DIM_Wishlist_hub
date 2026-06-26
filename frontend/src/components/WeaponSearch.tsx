import { Fragment, useEffect, useRef, useState } from "react";
import { api, ELEM_VAR } from "../api";
import type { FacetOption, FilterFacets, PerkLite, SearchHelp, WeaponFilters, WeaponSummary } from "../api";
import { STAT_LABEL } from "./StatsPanel";
import {
  ammoLabel,
  damageLabel,
  displayName,
  formatTemplate,
  slotLabel,
  tierLabel,
  useLanguage,
  weaponTypeLabel,
} from "../i18n";

function useToggleSet<T extends number | string>() {
  const [vals, setVals] = useState<T[]>([]);
  const toggle = (v: T) =>
    setVals((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));
  const clear = () => setVals([]);
  return { vals, toggle, clear, has: (v: T) => vals.includes(v) };
}

const STAT_FILTER_KEYS = [
  "range", "stability", "handling", "reload", "impact", "aim_assist",
  "magazine", "rpm", "recoil", "zoom", "charge_time", "draw_time",
  "blast_radius", "velocity", "swing_speed",
];

type PerkChip = PerkLite & { exclude: boolean };
type SectionId = "perks" | "advanced" | "type" | "frame" | "tier" | "slot" | "ammo" | "season" | "origin" | "stats";

const DEFAULT_ORDER: SectionId[] = ["perks", "advanced", "type", "frame", "tier", "slot", "ammo", "season", "origin", "stats"];
const ORDER_KEY = "dimhub.filterOrder";
const SECTION_IDS = ["element", ...DEFAULT_ORDER];
const COLLAPSE_KEY = "dimhub.filterCollapsed";
const DEFAULT_COLLAPSED = ["advanced", "season", "origin", "stats"];

function loadCollapsed(): Set<string> {
  try {
    const saved = localStorage.getItem(COLLAPSE_KEY);
    if (saved) return new Set(JSON.parse(saved) as string[]);
  } catch { /* ignore */ }
  return new Set(DEFAULT_COLLAPSED);
}

function normalizeOrder(raw: string[]): SectionId[] {
  const aliases: Record<string, SectionId> = {
    "퍽": "perks",
    "고급검색": "advanced",
    "종류": "type",
    "프레임": "frame",
    "등급": "tier",
    "슬롯": "slot",
    "탄약": "ammo",
    "시즌": "season",
    "기원": "origin",
    "스탯": "stats",
  };
  const known = raw
    .map((id) => aliases[id] ?? id)
    .filter((id): id is SectionId => DEFAULT_ORDER.includes(id as SectionId));
  const unique = [...new Set(known)];
  const missing = DEFAULT_ORDER.filter((id) => !unique.includes(id));
  return unique.length ? [...unique, ...missing] : DEFAULT_ORDER;
}

function loadOrder(): SectionId[] {
  try {
    const saved = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]") as string[];
    return normalizeOrder(saved);
  } catch { /* ignore */ }
  return DEFAULT_ORDER;
}

export function WeaponSearch({
  activeHash,
  onSelect,
}: {
  activeHash?: number;
  onSelect: (w: WeaponSummary) => void;
}) {
  const { language, t } = useLanguage();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<WeaponSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [facets, setFacets] = useState<FilterFacets | null>(null);
  const [count, setCount] = useState(0);
  const SEARCH_LIMIT = 60;

  const elements = useToggleSet<string>();
  const types = useToggleSet<number>();
  const tiers = useToggleSet<number>();
  const slots = useToggleSet<string>();
  const ammo = useToggleSet<number>();
  const frames = useToggleSet<string>();
  const origins = useToggleSet<string>();
  const seasons = useToggleSet<number>();

  const [statFilters, setStatFilters] = useState<Record<string, { min?: string; max?: string }>>({});
  const [perkChips, setPerkChips] = useState<PerkChip[]>([]);
  const [perkQ, setPerkQ] = useState("");
  const [perkSug, setPerkSug] = useState<PerkLite[]>([]);
  const [advQuery, setAdvQuery] = useState("");
  const [showHelp, setShowHelp] = useState(false);
  const [help, setHelp] = useState<SearchHelp | null>(null);

  const [collapsed, setCollapsed] = useState<Set<string>>(loadCollapsed);
  useEffect(() => {
    try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...collapsed])); } catch { /* ignore */ }
  }, [collapsed]);
  const isOpen = (id: string) => !collapsed.has(id);
  const toggleSection = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allCollapsed = SECTION_IDS.every((id) => collapsed.has(id));
  const toggleAll = () => setCollapsed(allCollapsed ? new Set() : new Set(SECTION_IDS));

  const [order, setOrder] = useState<SectionId[]>(loadOrder);
  const [showSettings, setShowSettings] = useState(false);
  useEffect(() => {
    try { localStorage.setItem(ORDER_KEY, JSON.stringify(order)); } catch { /* ignore */ }
  }, [order]);
  const moveSection = (id: SectionId, dir: -1 | 1) =>
    setOrder((prev) => {
      const i = prev.indexOf(id), j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  const resetOrder = () => setOrder(DEFAULT_ORDER);

  const [searchOpen, setSearchOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const headerRef = useRef<HTMLDivElement | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!searchOpen) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setSearchOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSearchOpen(false); };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [searchOpen]);

  useEffect(() => {
    if (!showFilters) return;
    const onDown = (e: MouseEvent) => {
      if (headerRef.current && !headerRef.current.contains(e.target as Node)) setShowFilters(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setShowFilters(false); };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [showFilters]);

  useEffect(() => {
    if (showHelp && !help) api.searchHelp().then(setHelp).catch(() => setHelp(null));
  }, [showHelp, help]);

  const statFilterCount = Object.values(statFilters).filter((v) => v.min || v.max).length;
  const activeFilterCount =
    elements.vals.length + types.vals.length + tiers.vals.length + slots.vals.length +
    ammo.vals.length + frames.vals.length + origins.vals.length + seasons.vals.length +
    statFilterCount + perkChips.length + (advQuery.trim() ? 1 : 0);

  const statKey = JSON.stringify(statFilters);
  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setLoading(true);
      setErr(null);
      const statMin: Record<string, number> = {};
      const statMax: Record<string, number> = {};
      for (const [k, v] of Object.entries(statFilters)) {
        if (v.min) statMin[k] = Number(v.min);
        if (v.max) statMax[k] = Number(v.max);
      }
      const filters: WeaponFilters = {
        damages: elements.vals,
        subtypes: types.vals,
        tiers: tiers.vals,
        slots: slots.vals,
        ammo: ammo.vals,
        frames: frames.vals,
        origins: origins.vals,
        seasons: seasons.vals,
        perks: perkChips.filter((p) => !p.exclude).map((p) => p.plug_hash),
        perkExclude: perkChips.filter((p) => p.exclude).map((p) => p.plug_hash),
        statMin,
        statMax,
        query: advQuery,
      };
      api.filters(q, filters).then(setFacets).catch(() => {});
      api
        .searchWeapons(q, filters)
        .then((rows) => {
          setResults(rows);
          if (rows.length < SEARCH_LIMIT) {
            setCount(rows.length);
          } else {
            api.countWeapons(q, filters).then((r) => setCount(r.count)).catch(() => setCount(rows.length));
          }
        })
        .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false));
    }, 220);
    return () => window.clearTimeout(timer.current);
  }, [q, elements.vals, types.vals, tiers.vals, slots.vals, ammo.vals,
      frames.vals, origins.vals, seasons.vals, statKey, perkChips, advQuery]);

  useEffect(() => {
    if (perkQ.trim().length < 1) {
      setPerkSug([]);
      return;
    }
    const tmo = window.setTimeout(() => {
      api.searchPerks(perkQ).then(setPerkSug).catch(() => setPerkSug([]));
    }, 200);
    return () => window.clearTimeout(tmo);
  }, [perkQ]);

  function addPerk(p: PerkLite) {
    if (!perkChips.some((c) => c.plug_hash === p.plug_hash)) {
      setPerkChips([...perkChips, { ...p, exclude: false }]);
    }
    setPerkQ("");
    setPerkSug([]);
  }
  function togglePerkMode(hash: number) {
    setPerkChips((prev) => prev.map((c) => (c.plug_hash === hash ? { ...c, exclude: !c.exclude } : c)));
  }
  function removePerk(hash: number) {
    setPerkChips((prev) => prev.filter((c) => c.plug_hash !== hash));
  }
  function setStat(key: string, side: "min" | "max", val: string) {
    setStatFilters((prev) => {
      const next = { ...prev, [key]: { ...prev[key], [side]: val } };
      if (!next[key].min && !next[key].max) delete next[key];
      return next;
    });
  }

  function clearAll() {
    elements.clear(); types.clear(); tiers.clear(); slots.clear(); ammo.clear();
    frames.clear(); origins.clear(); seasons.clear();
    setStatFilters({}); setPerkChips([]); setAdvQuery("");
  }

  function sectionTitle(id: string): string {
    const s = t.search.sections;
    return s[id as keyof typeof s] || id;
  }

  function facetLabel(id: string, option: FacetOption): string {
    if (id === "element") return damageLabel(String(option.value), t, option.label);
    if (id === "type") return weaponTypeLabel(Number(option.value), t, option.label);
    if (id === "tier") return tierLabel(Number(option.value), t, option.label);
    if (id === "slot") return slotLabel(String(option.value), t, option.label);
    if (id === "ammo") return ammoLabel(Number(option.value), t, option.label);
    return option.label;
  }

  function Section({
    id, title, selectedCount = 0, headerExtra, children,
  }: {
    id: string;
    title: string;
    selectedCount?: number;
    headerExtra?: React.ReactNode;
    children: React.ReactNode;
  }) {
    const open = isOpen(id);
    return (
      <div className="facet-group">
        <div className="facet-header" onClick={() => toggleSection(id)}>
          <span className="facet-caret">{open ? "▾" : "▸"}</span>
          <span className="facet-title">{title}</span>
          {selectedCount > 0 && <span className="facet-sel">{selectedCount}</span>}
          {headerExtra}
        </div>
        {open && children}
      </div>
    );
  }

  function ChipGroup({
    id, title, opts, has, toggle, accent, selectedCount = 0,
  }: {
    id: string;
    title: string;
    opts: FacetOption[];
    has: (v: any) => boolean;
    toggle: (v: any) => void;
    accent?: (o: FacetOption) => string | undefined;
    selectedCount?: number;
  }) {
    if (!opts || opts.length === 0) return null;
    return (
      <Section id={id} title={title} selectedCount={selectedCount}>
        <div className="facet-chips">
          {opts.map((o) => {
            const on = has(o.value);
            const color = accent?.(o);
            const label = facetLabel(id, o);
            return (
              <button
                key={String(o.value)}
                className={`facet-chip ${on ? "on" : ""}`}
                style={color ? ({ ["--chip-accent" as any]: color } as React.CSSProperties) : undefined}
                onClick={() => toggle(o.value)}
                title={`${label} · ${o.count} ${t.search.countUnit}`}
              >
                {color && <span className="facet-dot" />}
                {label}
                <span className="facet-count">{o.count}</span>
              </button>
            );
          })}
        </div>
      </Section>
    );
  }

  return (
    <div className="header-search" ref={headerRef}>
      <div className="search-box" ref={boxRef}>
        <input
          className="search-input"
          placeholder={t.search.placeholder}
          value={q}
          onChange={(e) => { setQ(e.target.value); setSearchOpen(true); }}
          onFocus={() => setSearchOpen(true)}
        />
        {searchOpen && (
          <div className="search-dropdown">
            <div className="dropdown-count">
              {count.toLocaleString()} {t.search.matchedWeapons}
              {count > SEARCH_LIMIT ? ` · ${formatTemplate(t.search.topShown, { limit: SEARCH_LIMIT })}` : ""}
            </div>
            {loading && results.length === 0 && <div className="hint" style={{ padding: "8px 10px" }}>{t.search.loading}</div>}
            {!loading && results.length === 0 && <div className="hint" style={{ padding: "8px 10px" }}>{t.search.noResults}</div>}
            {results.map((w) => {
              const type = weaponTypeLabel(w.weapon_subtype, t, w.type_label);
              const damage = damageLabel(w.default_damage_type, t, w.damage_label);
              const rarity = tierLabel(w.tier, t, w.tier_label);
              return (
                <button
                  key={w.item_hash}
                  className={`weapon-row ${w.item_hash === activeHash ? "active" : ""}`}
                  onClick={() => { onSelect(w); setSearchOpen(false); }}
                >
                  {w.icon ? <img className="icon" src={w.icon} alt="" /> : <div className="icon" />}
                  <div className="meta">
                    <span className="name">
                      {displayName(w, language)}
                      {w.has_holofoil && (
                        <span className="variant-badge" title={`${t.labels.holofoil} - ${t.labels.samePerkRoll}`}>
                          <span className="holo">✦ {t.labels.holofoil}</span>
                        </span>
                      )}
                      {w.has_adept && (
                        <span className="variant-badge"><span className="adept">A {t.labels.adept}</span></span>
                      )}
                    </span>
                    <span className="sub">
                      {type}
                      {damage ? ` · ${damage}` : ""}
                      {rarity ? ` · ${rarity}` : ""}
                    </span>
                    <span className="season-line">
                      {w.watermark && <img className="season-wm" src={w.watermark} alt="" />}
                      {w.season_number ? (
                        <span className="season-chip" title={`${t.labels.season} ${w.season_number}: ${w.season_name ?? ""}`}>
                          S{w.season_number}
                          {w.season_name ? <span className="season-nm"> · {w.season_name}</span> : null}
                        </span>
                      ) : (
                        <span className="season-chip unknown">{t.labels.noSeasonInfo}</span>
                      )}
                      {w.season_count && w.season_count > 1 && (
                        <span className="season-tag" title={t.builder.seasonVariantTitle}>
                          {t.labels.reissued} {w.season_count} {t.labels.season}
                        </span>
                      )}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <button
        className={`hs-filter-btn ${showFilters ? "on" : ""}`}
        onClick={() => setShowFilters((s) => !s)}
      >
        ⚙ {t.search.filters} {activeFilterCount > 0 ? `(${activeFilterCount})` : ""} {showFilters ? "▲" : "▼"}
      </button>
      <span className="hs-count" title={t.search.matchedWeapons}>
        <b>{count.toLocaleString()}</b>
      </span>

      {showFilters && facets && (() => {
        const sectionMap: Record<SectionId, React.ReactNode> = {
          advanced: (
            <Section id="advanced" title={t.search.advanced}
              selectedCount={advQuery.trim() ? 1 : 0}
              headerExtra={
                <button className="adv-help-toggle"
                        onClick={(e) => { e.stopPropagation(); setShowHelp((s) => !s); }}>
                  {showHelp ? t.search.hideHelp : t.search.showHelp}
                </button>
              }>
              <input
                className="search-input adv-query"
                placeholder={t.search.advancedPlaceholder}
                value={advQuery}
                onChange={(e) => setAdvQuery(e.target.value)}
              />
              {showHelp && (
                <div className="adv-cheatsheet">
                  <div className="adv-line"><b>{t.search.operators}</b>: {help?.operators.join("  ·  ") ?? "and · or · not / - · ( )"}</div>
                  {(help?.keywords ?? []).map((k) => (
                    <div className="adv-line" key={k.token}>
                      <code>{k.token}</code> <span className="adv-ex">{k["예"]}</span>
                    </div>
                  ))}
                  {(help?.examples ?? []).length > 0 && (
                    <div className="adv-examples">
                      {help!.examples.map((ex) => (
                        <button key={ex} className="adv-example" onClick={() => setAdvQuery(ex)}>{ex}</button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Section>
          ),
          type: <ChipGroup id="type" title={sectionTitle("type")} opts={facets.types} has={types.has} toggle={types.toggle} selectedCount={types.vals.length} />,
          frame: <ChipGroup id="frame" title={sectionTitle("frame")} opts={facets.frames} has={frames.has} toggle={frames.toggle} selectedCount={frames.vals.length} />,
          tier: <ChipGroup id="tier" title={sectionTitle("tier")} opts={facets.tiers} has={tiers.has} toggle={tiers.toggle} selectedCount={tiers.vals.length} />,
          slot: <ChipGroup id="slot" title={sectionTitle("slot")} opts={facets.slots} has={slots.has} toggle={slots.toggle} selectedCount={slots.vals.length} />,
          ammo: <ChipGroup id="ammo" title={sectionTitle("ammo")} opts={facets.ammo} has={ammo.has} toggle={ammo.toggle} selectedCount={ammo.vals.length} />,
          season: <ChipGroup id="season" title={sectionTitle("season")} opts={facets.seasons} has={seasons.has} toggle={seasons.toggle} selectedCount={seasons.vals.length} />,
          origin: <ChipGroup id="origin" title={sectionTitle("origin")} opts={facets.origins} has={origins.has} toggle={origins.toggle} selectedCount={origins.vals.length} />,
          stats: (
            <Section id="stats" title={t.search.statSection} selectedCount={statFilterCount}>
              <div className="stat-filter-grid">
                {STAT_FILTER_KEYS.map((k) => (
                  <div className="stat-filter-row" key={k}>
                    <span className="stat-filter-name">{STAT_LABEL[k] || k}</span>
                    <input type="number" className="stat-filter-input" placeholder=">=" min={0} max={100}
                           value={statFilters[k]?.min ?? ""} onChange={(e) => setStat(k, "min", e.target.value)} />
                    <input type="number" className="stat-filter-input" placeholder="<=" min={0} max={100}
                           value={statFilters[k]?.max ?? ""} onChange={(e) => setStat(k, "max", e.target.value)} />
                  </div>
                ))}
              </div>
            </Section>
          ),
          perks: (
            <Section id="perks" title={t.search.perkSection} selectedCount={perkChips.length}>
              <div className="filter-perk">
                <input className="search-input" placeholder={t.search.perkPlaceholder}
                       value={perkQ} onChange={(e) => setPerkQ(e.target.value)} />
                {perkSug.length > 0 && (
                  <div className="perk-sug">
                    {perkSug.map((p) => (
                      <button key={p.plug_hash} className="perk-sug-item" onClick={() => addPerk(p)}>
                        {displayName(p, language)}
                      </button>
                    ))}
                  </div>
                )}
                {perkChips.length > 0 && (
                  <div className="tag-chips" style={{ marginTop: 6, flexWrap: "wrap" }}>
                    {perkChips.map((p) => (
                      <span key={p.plug_hash} className={`chip on perk-mode ${p.exclude ? "exclude" : ""}`}>
                        <button className="perk-mode-toggle" onClick={() => togglePerkMode(p.plug_hash)}
                                title={p.exclude ? t.search.excludedTitle : t.search.ownedTitle}>
                          {p.exclude ? "⊘" : "✓"}
                        </button>
                        {displayName(p, language)}
                        <button className="perk-remove" onClick={() => removePerk(p.plug_hash)}>✕</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </Section>
          ),
        };
        return (
        <div className="filter-popover">
          <ChipGroup
            id="element" title={sectionTitle("element")}
            opts={facets.elements}
            has={elements.has}
            toggle={elements.toggle}
            selectedCount={elements.vals.length}
            accent={(o) => (ELEM_VAR[o.value as string] ? `var(${ELEM_VAR[o.value as string]})` : undefined)}
          />
          <div className="filter-toolbar">
            <button className="filter-toolbar-btn" onClick={toggleAll}>
              {allCollapsed ? `⊞ ${t.search.expandAll}` : `⊟ ${t.search.collapseAll}`}
            </button>
            <button className={`filter-toolbar-btn ${showSettings ? "on" : ""}`} onClick={() => setShowSettings((s) => !s)}>
              ⚙ {t.search.filterLayout}
            </button>
            {activeFilterCount > 0 && (
              <button className="filter-toolbar-btn" onClick={clearAll}>{t.search.clearFilters} ({activeFilterCount})</button>
            )}
          </div>

          {showSettings && (
            <div className="filter-settings">
              <div className="facet-title">{t.search.layoutHint}</div>
              {order.map((id, i) => (
                <div className="settings-row" key={id}>
                  <span className="settings-name">{sectionTitle(id)}</span>
                  <button className="settings-move" disabled={i === 0} onClick={() => moveSection(id, -1)} title={t.search.moveUp}>▲</button>
                  <button className="settings-move" disabled={i === order.length - 1} onClick={() => moveSection(id, 1)} title={t.search.moveDown}>▼</button>
                </div>
              ))}
              <button className="filter-toolbar-btn" style={{ marginTop: 6 }} onClick={resetOrder}>{t.search.resetOrder}</button>
            </div>
          )}

          {order.map((id) => <Fragment key={id}>{sectionMap[id]}</Fragment>)}
        </div>
        );
      })()}

      {err && <div className="hs-error">{t.search.error}: {err}</div>}
    </div>
  );
}