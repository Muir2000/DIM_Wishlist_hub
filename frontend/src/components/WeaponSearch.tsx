import { Fragment, useEffect, useRef, useState } from "react";
import { api, ELEM_VAR } from "../api";
import type { FacetOption, FilterFacets, PerkLite, SearchHelp, WeaponFilters, WeaponSummary } from "../api";
import { STAT_LABEL } from "./StatsPanel";

// 토글 가능한 값 집합 (선택/해제)
function useToggleSet<T extends number | string>() {
  const [vals, setVals] = useState<T[]>([]);
  const toggle = (v: T) =>
    setVals((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));
  const clear = () => setVals([]);
  return { vals, toggle, clear, has: (v: T) => vals.includes(v) };
}

// 스탯 필터에 노출할 키(자주 쓰는 것 우선)
const STAT_FILTER_KEYS = [
  "range", "stability", "handling", "reload", "impact", "aim_assist",
  "magazine", "rpm", "recoil", "zoom", "charge_time", "draw_time",
  "blast_radius", "velocity", "swing_speed",
];

type PerkChip = PerkLite & { exclude: boolean };

// 패널 내부 재배치 가능한 섹션 순서 (퍽을 최상단으로). 속성은 패널 밖 고정 노출.
const DEFAULT_ORDER = ["퍽", "고급검색", "종류", "프레임", "등급", "슬롯", "탄약", "시즌", "기원", "스탯"];
const SECTION_TITLES: Record<string, string> = {
  퍽: "퍽", 고급검색: "고급 검색", 종류: "종류", 프레임: "프레임", 등급: "등급",
  슬롯: "슬롯", 탄약: "탄약", 시즌: "시즌", 기원: "기원 특성", 스탯: "스탯",
};
const ORDER_KEY = "dimhub.filterOrder";
// 접기 영속화 (속성 포함 전체)
const SECTION_IDS = ["속성", ...DEFAULT_ORDER];
const COLLAPSE_KEY = "dimhub.filterCollapsed";
const DEFAULT_COLLAPSED = ["고급검색", "시즌", "기원", "스탯"];

function loadCollapsed(): Set<string> {
  try {
    const saved = localStorage.getItem(COLLAPSE_KEY);
    if (saved) return new Set(JSON.parse(saved) as string[]);
  } catch { /* ignore */ }
  return new Set(DEFAULT_COLLAPSED);
}

function loadOrder(): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(ORDER_KEY) || "[]") as string[];
    const known = saved.filter((id) => DEFAULT_ORDER.includes(id));
    const missing = DEFAULT_ORDER.filter((id) => !known.includes(id));  // 새 섹션은 뒤에 추가
    if (known.length) return [...known, ...missing];
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
  const [q, setQ] = useState("");
  const [results, setResults] = useState<WeaponSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [facets, setFacets] = useState<FilterFacets | null>(null);
  const [count, setCount] = useState(0);          // 현재 필터/검색에 매칭된 총 건수
  const SEARCH_LIMIT = 60;

  // 카테고리별 선택 집합
  const elements = useToggleSet<string>();   // 속성
  const types = useToggleSet<number>();      // 종류
  const tiers = useToggleSet<number>();      // 등급
  const slots = useToggleSet<string>();      // 슬롯
  const ammo = useToggleSet<number>();       // 탄약
  const frames = useToggleSet<string>();     // 프레임
  const origins = useToggleSet<string>();    // 기원 특성
  const seasons = useToggleSet<number>();    // 시즌

  // 스탯 필터 {key: {min, max}} + 퍽 칩(보유/제외) + 고급 텍스트 쿼리
  const [statFilters, setStatFilters] = useState<Record<string, { min?: string; max?: string }>>({});
  const [perkChips, setPerkChips] = useState<PerkChip[]>([]);
  const [perkQ, setPerkQ] = useState("");
  const [perkSug, setPerkSug] = useState<PerkLite[]>([]);
  const [advQuery, setAdvQuery] = useState("");
  const [showHelp, setShowHelp] = useState(false);
  const [help, setHelp] = useState<SearchHelp | null>(null);

  // 카테고리 접기 — 기본은 길거나 고급인 섹션을 접어 두고, 상태는 localStorage 에 보존.
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

  // 필터 배치(순서) — 설정 패널에서 변경, localStorage 보존.
  const [order, setOrder] = useState<string[]>(loadOrder);
  const [showSettings, setShowSettings] = useState(false);
  useEffect(() => {
    try { localStorage.setItem(ORDER_KEY, JSON.stringify(order)); } catch { /* ignore */ }
  }, [order]);
  const moveSection = (id: string, dir: -1 | 1) =>
    setOrder((prev) => {
      const i = prev.indexOf(id), j = i + dir;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  const resetOrder = () => setOrder(DEFAULT_ORDER);

  // 검색 자동완성 드롭다운 (플로팅) — 입력/포커스 시 열고, 외부클릭·선택·ESC 시 닫음
  const [searchOpen, setSearchOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const headerRef = useRef<HTMLDivElement | null>(null);  // 필터 팝오버 외부클릭 감지

  const timer = useRef<number | undefined>(undefined);

  // 패싯은 현재 검색/필터에 맞춰 매 검색마다 갱신(아래 검색 effect 에서 호출)

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

  // 필터 팝오버: 외부클릭/ESC 시 닫기
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
      // 패싯도 현재 검색/필터 기준으로 갱신(컨텍스트 인지)
      api.filters(q, filters).then(setFacets).catch(() => {});
      api
        .searchWeapons(q, filters)
        .then((rows) => {
          setResults(rows);
          // 결과가 상한 미만이면 그 길이가 곧 총 건수; 상한이면 별도 카운트 조회
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
    const t = window.setTimeout(() => {
      api.searchPerks(perkQ).then(setPerkSug).catch(() => setPerkSug([]));
    }, 200);
    return () => window.clearTimeout(t);
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

  // 접이식 섹션 래퍼 (헤더 클릭으로 토글, 선택 수 배지)
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

  // 칩 그룹 렌더 헬퍼 (접이식)
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
            return (
              <button
                key={String(o.value)}
                className={`facet-chip ${on ? "on" : ""}`}
                style={color ? ({ ["--chip-accent" as any]: color } as React.CSSProperties) : undefined}
                onClick={() => toggle(o.value)}
                title={`${o.label} · ${o.count}종`}
              >
                {color && <span className="facet-dot" />}
                {o.label}
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
          placeholder="무기 이름 검색 (한글/영문)…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setSearchOpen(true); }}
          onFocus={() => setSearchOpen(true)}
        />
        {searchOpen && (
          <div className="search-dropdown">
            <div className="dropdown-count">
              {count.toLocaleString()}개 무기
              {count > SEARCH_LIMIT ? ` · 상위 ${SEARCH_LIMIT}개 표시` : ""}
            </div>
            {loading && results.length === 0 && <div className="hint" style={{ padding: "8px 10px" }}>검색 중…</div>}
            {!loading && results.length === 0 && <div className="hint" style={{ padding: "8px 10px" }}>결과 없음.</div>}
            {results.map((w) => (
              <button
                key={w.item_hash}
                className={`weapon-row ${w.item_hash === activeHash ? "active" : ""}`}
                onClick={() => { onSelect(w); setSearchOpen(false); }}
              >
                {w.icon ? <img className="icon" src={w.icon} alt="" /> : <div className="icon" />}
                <div className="meta">
                  <span className="name">
                    {w.name}
                    {w.has_holofoil && (
                      <span className="variant-badge" title="이 시즌에 홀로포일(외형만 다른 변형) 포함 — 동일 퍽롤">
                        <span className="holo">✦ 홀로포일</span>
                      </span>
                    )}
                    {w.has_adept && (
                      <span className="variant-badge"><span className="adept">A 숙련자</span></span>
                    )}
                  </span>
                  <span className="sub">
                    {w.type_label}
                    {w.damage_label ? ` · ${w.damage_label}` : ""}
                    {w.tier_label ? ` · ${w.tier_label}` : ""}
                  </span>
                  <span className="season-line">
                    {w.watermark && <img className="season-wm" src={w.watermark} alt="" />}
                    {w.season_number ? (
                      <span className="season-chip" title={`시즌 ${w.season_number}: ${w.season_name ?? ""}`}>
                        S{w.season_number}
                        {w.season_name ? <span className="season-nm"> · {w.season_name}</span> : null}
                      </span>
                    ) : (
                      <span className="season-chip unknown">시즌 정보 없음</span>
                    )}
                    {w.season_count && w.season_count > 1 && (
                      <span className="season-tag" title="이 무기는 여러 시즌(복각)으로 출시되었고 시즌마다 퍽풀이 다릅니다. 시즌별로 따로 표시됩니다.">
                        복각 {w.season_count}시즌
                      </span>
                    )}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <button
        className={`hs-filter-btn ${showFilters ? "on" : ""}`}
        onClick={() => setShowFilters((s) => !s)}
      >
        ⚙ 필터 {activeFilterCount > 0 ? `(${activeFilterCount})` : ""} {showFilters ? "▲" : "▼"}
      </button>
      <span className="hs-count" title="현재 필터/검색에 매칭된 무기 수">
        <b>{count.toLocaleString()}</b>개
      </span>

      {showFilters && facets && (() => {
        // 섹션 id → JSX (순서는 order 로 결정, 설정 패널에서 변경 가능)
        const sectionMap: Record<string, React.ReactNode> = {
          고급검색: (
            <Section id="고급검색" title="고급 검색 (DIM식 텍스트 쿼리)"
              selectedCount={advQuery.trim() ? 1 : 0}
              headerExtra={
                <button className="adv-help-toggle"
                        onClick={(e) => { e.stopPropagation(); setShowHelp((s) => !s); }}>
                  {showHelp ? "도움말 닫기" : "도움말 ?"}
                </button>
              }>
              <input
                className="search-input adv-query"
                placeholder={'예) is:핸드캐논 stat:range:>=50 -perkname:"무법자" season:>=23'}
                value={advQuery}
                onChange={(e) => setAdvQuery(e.target.value)}
              />
              {showHelp && (
                <div className="adv-cheatsheet">
                  <div className="adv-line"><b>연산자</b>: {help?.operators.join("  ·  ") ?? "and · or · not / - · ( )"}</div>
                  {(help?.keywords ?? []).map((k) => (
                    <div className="adv-line" key={k.token}>
                      <code>{k.token}</code> <span className="adv-ex">{k.예}</span>
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
          종류: <ChipGroup id="종류" title="종류" opts={facets.types} has={types.has} toggle={types.toggle} selectedCount={types.vals.length} />,
          프레임: <ChipGroup id="프레임" title="프레임(아키타입)" opts={facets.frames} has={frames.has} toggle={frames.toggle} selectedCount={frames.vals.length} />,
          등급: <ChipGroup id="등급" title="등급" opts={facets.tiers} has={tiers.has} toggle={tiers.toggle} selectedCount={tiers.vals.length} />,
          슬롯: <ChipGroup id="슬롯" title="슬롯" opts={facets.slots} has={slots.has} toggle={slots.toggle} selectedCount={slots.vals.length} />,
          탄약: <ChipGroup id="탄약" title="탄약" opts={facets.ammo} has={ammo.has} toggle={ammo.toggle} selectedCount={ammo.vals.length} />,
          시즌: <ChipGroup id="시즌" title="시즌(복각)" opts={facets.seasons} has={seasons.has} toggle={seasons.toggle} selectedCount={seasons.vals.length} />,
          기원: <ChipGroup id="기원" title="기원 특성" opts={facets.origins} has={origins.has} toggle={origins.toggle} selectedCount={origins.vals.length} />,
          스탯: (
            <Section id="스탯" title="스탯 (≥ / ≤)" selectedCount={statFilterCount}>
              <div className="stat-filter-grid">
                {STAT_FILTER_KEYS.map((k) => (
                  <div className="stat-filter-row" key={k}>
                    <span className="stat-filter-name">{STAT_LABEL[k] || k}</span>
                    <input type="number" className="stat-filter-input" placeholder="≥" min={0} max={100}
                           value={statFilters[k]?.min ?? ""} onChange={(e) => setStat(k, "min", e.target.value)} />
                    <input type="number" className="stat-filter-input" placeholder="≤" min={0} max={100}
                           value={statFilters[k]?.max ?? ""} onChange={(e) => setStat(k, "max", e.target.value)} />
                  </div>
                ))}
              </div>
            </Section>
          ),
          퍽: (
            <Section id="퍽" title="퍽 (클릭 시 보유↔제외 전환)" selectedCount={perkChips.length}>
              <div className="filter-perk">
                <input className="search-input" placeholder="퍽 이름으로 필터…"
                       value={perkQ} onChange={(e) => setPerkQ(e.target.value)} />
                {perkSug.length > 0 && (
                  <div className="perk-sug">
                    {perkSug.map((p) => (
                      <button key={p.plug_hash} className="perk-sug-item" onClick={() => addPerk(p)}>
                        {p.name}
                      </button>
                    ))}
                  </div>
                )}
                {perkChips.length > 0 && (
                  <div className="tag-chips" style={{ marginTop: 6, flexWrap: "wrap" }}>
                    {perkChips.map((p) => (
                      <span key={p.plug_hash} className={`chip on perk-mode ${p.exclude ? "exclude" : ""}`}>
                        <button className="perk-mode-toggle" onClick={() => togglePerkMode(p.plug_hash)}
                                title={p.exclude ? "제외 중 — 클릭하면 보유로" : "보유 중 — 클릭하면 제외로"}>
                          {p.exclude ? "⊘" : "✓"}
                        </button>
                        {p.name}
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
            id="속성" title="속성"
            opts={facets.elements}
            has={elements.has}
            toggle={elements.toggle}
            selectedCount={elements.vals.length}
            accent={(o) => (ELEM_VAR[o.value as string] ? `var(${ELEM_VAR[o.value as string]})` : undefined)}
          />
          <div className="filter-toolbar">
            <button className="filter-toolbar-btn" onClick={toggleAll}>
              {allCollapsed ? "⊞ 모두 펼치기" : "⊟ 모두 접기"}
            </button>
            <button className={`filter-toolbar-btn ${showSettings ? "on" : ""}`} onClick={() => setShowSettings((s) => !s)}>
              ⚙ 배치
            </button>
            {activeFilterCount > 0 && (
              <button className="filter-toolbar-btn" onClick={clearAll}>필터 전체 해제 ({activeFilterCount})</button>
            )}
          </div>

          {showSettings && (
            <div className="filter-settings">
              <div className="facet-title">필터 배치 — 위/아래로 순서 변경 (자동 저장)</div>
              {order.map((id, i) => (
                <div className="settings-row" key={id}>
                  <span className="settings-name">{SECTION_TITLES[id] ?? id}</span>
                  <button className="settings-move" disabled={i === 0} onClick={() => moveSection(id, -1)} title="위로">▲</button>
                  <button className="settings-move" disabled={i === order.length - 1} onClick={() => moveSection(id, 1)} title="아래로">▼</button>
                </div>
              ))}
              <button className="filter-toolbar-btn" style={{ marginTop: 6 }} onClick={resetOrder}>기본 순서로</button>
            </div>
          )}

          {order.map((id) => <Fragment key={id}>{sectionMap[id]}</Fragment>)}
        </div>
        );
      })()}

      {err && <div className="hs-error">오류: {err}</div>}
    </div>
  );
}
