"""Bungie Destiny 2 매니페스트 -> 로컬 SQLite 적재기 (Phase 1).

전략(계획서 기준):
  * GET /Platform/Destiny2/Manifest/ 로 version 과 jsonWorldComponentContentPaths 획득.
  * 저장된 version 과 같으면 스킵(--force 로 강제).
  * JSON 컴포넌트 방식으로 필요한 테이블만 다운로드(SQLite .content 의 signed-int 변환 회피):
      - DestinyInventoryItemDefinition (ko)  : 무기/퍼크 이름·아이콘·소켓
      - DestinyInventoryItemDefinition (en)  : 검색용 영문 이름 (선택)
      - DestinyPlugSetDefinition       (ko)  : 랜덤 롤 퍼크 풀
  * 무기 필터: itemType==3 또는 itemCategoryHashes 에 1 포함, tierType ∈ {5,6}, redacted 제외.
  * 퍼크 열: sockets.socketCategories 중 socketCategoryHash==4241085061(WeaponPerks)의
    socketIndexes 를 순회 → randomizedPlugSetHash > reusablePlugSetHash > inline reusablePlugItems
    순으로 풀 해석 → DestinyPlugSetDefinition.reusablePlugItems(plugItemHash, currentlyCanRoll).
  * 소켓 인덱스를 하드코딩하지 않고 plug 의 plugCategoryIdentifier 로 열 종류 판별.

실행 (repo 루트에서):
    python -m ingest.manifest_ingest            # version 변경 시에만
    python -m ingest.manifest_ingest --force    # 강제 재적재
    python -m ingest.manifest_ingest --limit 200  # 일부만(개발용)
"""
from __future__ import annotations

import argparse
import gc
from datetime import datetime, timezone

from . import _bootstrap_path  # noqa: F401  (sys.path 보정)

import httpx  # noqa: E402
from app import config, db  # noqa: E402

WEAPON_PERKS_CATEGORY = 4241085061  # DIM SocketCategoryHashes.WeaponPerks
INTRINSIC_CATEGORY = 3956125808

# 퍼크가 아닌 plug(트래커/마스터워크/셰이더/장식/메멘토/고유)는 열에서 제외.
# plugCategoryIdentifier 에 아래 부분 문자열이 있으면 스킵. (실제 퍼크 카테고리는 barrels/
# magazines/frames/origins/sights 등으로 아래 단어를 포함하지 않음.)
DENY_PLUGCAT = ("tracker", "shader", "skins", "ornament", "memento", "masterwork", "intrinsic")

DAMAGE_TYPE = {0: None, 1: "Kinetic", 2: "Arc", 3: "Solar", 4: "Void", 6: "Stasis", 7: "Strand"}
SLOT_BY_CATEGORY = {2: "Kinetic", 3: "Energy", 4: "Power"}
WEAPON_CATEGORY_HASH = 1

# Bungie statHash -> 정규화 키 (seed/build_seed 와 동일 키 사용)
STAT_KEYS = {
    4043523819: "impact",
    1240592695: "range",
    155624089: "stability",
    943549884: "handling",
    4188031367: "reload",
    3871231066: "magazine",
    1345867579: "aim_assist",
    2715839340: "recoil",
    3022809290: "zoom",
    4284893561: "rpm",
    2961396640: "charge_time",   # 융합소총
    447667954: "draw_time",      # 활
    2837207746: "swing_speed",   # 검
    3614673599: "blast_radius",  # 로켓/유탄
    2523465841: "velocity",
}


def _interp(value, points):
    """investment value -> display value (piecewise-linear). points 없으면 raw 반환."""
    if not points:
        return value
    pts = sorted(points, key=lambda p: p.get("value", 0))
    if value <= pts[0].get("value", 0):
        return pts[0].get("weight", value)
    if value >= pts[-1].get("value", 0):
        return pts[-1].get("weight", value)
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        av, bv = a.get("value", 0), b.get("value", 0)
        if av <= value <= bv:
            if bv == av:
                return a.get("weight", value)
            t = (value - av) / (bv - av)
            return round(a.get("weight", 0) + t * (b.get("weight", 0) - a.get("weight", 0)))
    return pts[-1].get("weight", value)


def _build_interp(stat_groups: dict) -> dict:
    """statGroupHash -> { statHash -> [interpolation points] }."""
    out = {}
    for k, g in stat_groups.items():
        m = {}
        for sd in g.get("scaledStats", []):
            sh = sd.get("statHash") or sd.get("statTypeHash")
            if sh is not None:
                m[int(sh)] = sd.get("displayInterpolation", [])
        out[int(k)] = m
    return out


def _client() -> httpx.Client:
    if not config.BUNGIE_API_KEY:
        raise SystemExit(
            "BUNGIE_API_KEY 가 설정되지 않았습니다. .env 에 키를 넣으세요 "
            "(https://www.bungie.net/en/Application 에서 발급)."
        )
    return httpx.Client(
        base_url=config.BUNGIE_ROOT,
        headers={"X-API-Key": config.BUNGIE_API_KEY},
        timeout=120.0,
    )


def fetch_manifest(client: httpx.Client) -> dict:
    r = client.get("/Platform/Destiny2/Manifest/")
    r.raise_for_status()
    return r.json()["Response"]


def fetch_component(client: httpx.Client, rel_url: str) -> dict:
    r = client.get(rel_url)
    r.raise_for_status()
    return r.json()


def column_kind_from_identifier(identifier: str) -> str:
    s = (identifier or "").lower()
    if any(k in s for k in ("barrel", "sight", "scope", "bowstring", "blade", "haft", "launcher")):
        return "barrel"
    if any(k in s for k in ("magazine", "mag", "battery", "arrow", "guard", "tube", "ammo", "clip")):
        return "magazine"
    if "origin" in s:
        return "origin"
    if "intrinsic" in s:
        return "intrinsic"
    return "trait"


def _watermark(item: dict) -> str:
    q = item.get("quality") or {}
    icons = q.get("displayVersionWatermarkIcons") or []
    cur = q.get("currentVersion")
    if icons and isinstance(cur, int) and 0 <= cur < len(icons) and icons[cur]:
        return icons[cur]
    return item.get("iconWatermark") or item.get("iconWatermarkShelved") or None


def _is_weapon(item: dict) -> bool:
    # itemType==3(Weapon) 만 진짜 무기. itemType 20(Dummy)/27(Wrapper) 등 컬렉션 더미·
    # 벤더 프리뷰는 무기 카테고리 해시를 갖더라도 제외(이름만 같은 가짜가 빌더에 끼는 것 방지).
    if item.get("redacted"):
        return False
    if item.get("itemType") != 3:
        return False
    # 장착 가능한 실아이템만 (더미/래퍼는 보통 sockets 가 없음)
    return bool(item.get("sockets"))


def _slot(item: dict) -> str:
    for c in item.get("itemCategoryHashes") or []:
        if c in SLOT_BY_CATEGORY:
            return SLOT_BY_CATEGORY[c]
    return None


def _resolve_pool(entry: dict, plugsets: dict):
    """소켓 엔트리 -> [(plug_hash, currently_can_roll), ...]."""
    h = entry.get("randomizedPlugSetHash") or entry.get("reusablePlugSetHash")
    if h:
        ps = plugsets.get(str(h)) or plugsets.get(h)
        if ps:
            return [
                (p["plugItemHash"], bool(p.get("currentlyCanRoll", True)))
                for p in ps.get("reusablePlugItems", [])
            ]
    # inline
    return [(p["plugItemHash"], True) for p in entry.get("reusablePlugItems", [])]


def ingest(force: bool = False, limit: int = 0) -> None:
    client = _client()
    manifest = fetch_manifest(client)
    version = manifest["version"]

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = db.connect(config.DB_PATH)
    db.apply_schema(conn)

    row = conn.execute("SELECT version FROM manifest_meta WHERE id=1").fetchone()
    if row and row["version"] == version and not force:
        print(f"매니페스트가 최신입니다 (version={version}). 스킵. --force 로 강제 가능.")
        conn.close()
        return

    comp = manifest["jsonWorldComponentContentPaths"]
    locale = config.MANIFEST_LOCALE if config.MANIFEST_LOCALE in comp else "en"
    fb = config.MANIFEST_LOCALE_FALLBACK if config.MANIFEST_LOCALE_FALLBACK in comp else None

    print(f"[1/4] 영문 이름·설명 적재 (locale={fb}) ...")
    en_names = {}
    en_descs = {}
    if fb and fb != locale:
        en_items = fetch_component(client, comp[fb]["DestinyInventoryItemDefinition"])
        for k, it in en_items.items():
            dp = it.get("displayProperties") or {}
            nm = dp.get("name")
            desc = dp.get("description")
            if nm:
                en_names[int(k)] = nm
            if desc:
                en_descs[int(k)] = desc
        del en_items
        gc.collect()

    print(f"[2/4] 아이템 정의 적재 (locale={locale}) ...")
    items = fetch_component(client, comp[locale]["DestinyInventoryItemDefinition"])

    print("[3/5] PlugSet 정의 적재 ...")
    plugsets = fetch_component(client, comp[locale]["DestinyPlugSetDefinition"])

    print("[4/5] 스탯 정의 적재 ...")
    stat_defs_raw = fetch_component(client, comp[locale]["DestinyStatDefinition"])
    stat_groups = fetch_component(client, comp[locale]["DestinyStatGroupDefinition"])
    interp = _build_interp(stat_groups)

    print("[5/5] 정제 후 DB 기록 ...")
    cur = conn.cursor()
    # 재적재: 기존 무기/퍼크/스탯/롤 비우기 (roll_stats 의 community 소스는 보존)
    cur.execute("DELETE FROM weapon_perks")
    cur.execute("DELETE FROM weapons")
    cur.execute("DELETE FROM perks")
    cur.execute("DELETE FROM weapon_stats")
    cur.execute("DELETE FROM perk_stats")
    cur.execute("DELETE FROM stat_defs")

    for sh, key in STAT_KEYS.items():
        sd = stat_defs_raw.get(str(sh)) or {}
        nm = (sd.get("displayProperties") or {}).get("name")
        cur.execute(
            "INSERT OR REPLACE INTO stat_defs (stat_hash,key,name_ko,name_en) VALUES (?,?,?,?)",
            (sh, key, nm, en_names.get(sh) or nm),
        )

    def perk_def(plug_hash):
        return items.get(str(plug_hash)) or items.get(plug_hash)

    n_weapons = 0
    for k, item in items.items():
        if not _is_weapon(item):
            continue
        tier = (item.get("inventory") or {}).get("tierType")
        if tier not in (5, 6):
            continue
        item_hash = int(k)
        dp = item.get("displayProperties") or {}

        # 고유 프레임(intrinsic) 추출: IntrinsicTraits 소켓의 singleInitialItemHash → 그 플러그 이름
        frame_name, frame_hash = None, None
        _sk = item.get("sockets") or {}
        _entries = _sk.get("socketEntries") or []
        _intr = []
        for cat in _sk.get("socketCategories") or []:
            if cat.get("socketCategoryHash") == INTRINSIC_CATEGORY:
                _intr += cat.get("socketIndexes") or []
        for sidx in _intr:
            if sidx < len(_entries):
                h = _entries[sidx].get("singleInitialItemHash")
                pd = perk_def(h) if h else None
                if pd:
                    frame_name = (pd.get("displayProperties") or {}).get("name")
                    frame_hash = h
                    break

        # 변형 그룹 키: 같은 이름+서브타입 = 복각/홀로포일/에이뎁트 한 묶음.
        # 위시리스트는 hash 로 매칭하므로, 내보낼 때 이 그룹 전원에게 같은 줄을 emit 한다.
        subtype = item.get("itemSubType")
        gname = en_names.get(item_hash) or dp.get("name") or str(item_hash)
        variant_group = f"{gname}|{subtype}"

        cur.execute(
            """INSERT OR REPLACE INTO weapons
               (item_hash,name_ko,name_en,icon,watermark,tier,weapon_subtype,
                ammo_type,slot,default_damage_type,frame,frame_hash,
                is_holofoil,is_adept,is_featured,variant_group,redacted)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
            (item_hash, dp.get("name"), en_names.get(item_hash), dp.get("icon"),
             _watermark(item), tier, subtype,
             (item.get("equippingBlock") or {}).get("ammoType"),
             _slot(item), DAMAGE_TYPE.get(item.get("defaultDamageType")),
             frame_name, frame_hash,
             1 if item.get("isHolofoil") else 0,
             1 if item.get("isAdept") else 0,
             1 if item.get("isFeaturedItem") else 0,
             variant_group),
        )

        # 무기 표시 스탯: investment value -> statGroup 보간(scaledStats 없으면 raw)
        stat_block = item.get("stats") or {}
        gmap = interp.get(stat_block.get("statGroupHash"), {})
        for sh_str, st in (stat_block.get("stats") or {}).items():
            sh = int(sh_str)
            key = STAT_KEYS.get(sh)
            if not key:
                continue
            raw = st.get("value", 0)
            pts = gmap.get(sh)
            disp = _interp(raw, pts) if pts else raw
            cur.execute(
                "INSERT OR REPLACE INTO weapon_stats (weapon_hash,stat_key,value) VALUES (?,?,?)",
                (item_hash, key, disp),
            )

        sockets = item.get("sockets") or {}
        entries = sockets.get("socketEntries") or []
        cat_indexes = []
        for cat in sockets.get("socketCategories") or []:
            if cat.get("socketCategoryHash") == WEAPON_PERKS_CATEGORY:
                cat_indexes.extend(cat.get("socketIndexes") or [])

        col_idx = 0
        for sidx in cat_indexes:
            if sidx >= len(entries):
                continue
            entry = entries[sidx]
            curated = entry.get("singleInitialItemHash") or 0
            pool = _resolve_pool(entry, plugsets)
            if not pool:
                continue

            # 플러그 정의 해석 + 코스메틱(트래커/마스터워크 등) 제외
            plugs = []  # (ph, can_roll, tier, pcat, name, pdef)
            for ph, can_roll in pool:
                pdef = perk_def(ph)
                if not pdef:
                    continue
                pcat = (pdef.get("plug") or {}).get("plugCategoryIdentifier") or ""
                if any(b in pcat for b in DENY_PLUGCAT):
                    continue
                tier = (pdef.get("inventory") or {}).get("tierType")
                nm = (pdef.get("displayProperties") or {}).get("name")
                plugs.append((ph, can_roll, tier, pcat, nm, pdef))
            if not plugs:
                continue  # 코스메틱만 있는 소켓(예: 트래커)은 열로 만들지 않음

            kind = column_kind_from_identifier(plugs[0][3])
            # 이름별 base(tier 2) 해시 — 강화(tier 3)→base 매핑 + 중복 제거 기준
            base_by_name = {}
            for ph, cr, tier, pcat, nm, pdef in plugs:
                if tier == 2 and nm and nm not in base_by_name:
                    base_by_name[nm] = ph

            chosen = {}  # name -> (ph, can_roll, tier) — 열에는 이름당 1개(base 우선)
            for ph, cr, tier, pcat, nm, pdef in plugs:
                is_enh = 1 if tier == 3 else 0
                base_h = base_by_name.get(nm) if (is_enh and base_by_name.get(nm) not in (None, ph)) else None
                pdp = pdef.get("displayProperties") or {}
                # 모든 plug 은 perks 에 기록(강화→base 매핑 보존; 인벤토리 매칭용)
                cur.execute(
                    """INSERT OR REPLACE INTO perks
                       (plug_hash,name_ko,name_en,description_ko,description_en,icon,plug_category,is_enhanced,base_plug_hash)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (ph, pdp.get("name"), en_names.get(ph),
                     pdp.get("description"), en_descs.get(ph),
                     pdp.get("icon"), pcat, is_enh, base_h),
                )
                for inv in (pdef.get("investmentStats") or []):
                    key = STAT_KEYS.get(inv.get("statTypeHash"))
                    if key:
                        cur.execute(
                            """INSERT OR REPLACE INTO perk_stats (plug_hash,stat_key,value,is_conditional)
                               VALUES (?,?,?,?)""",
                            (ph, key, inv.get("value", 0), 1 if inv.get("isConditionallyActive") else 0),
                        )
                k = nm if nm is not None else ph
                prev = chosen.get(k)
                if prev is None or (tier == 2 and prev[2] != 2):
                    chosen[k] = (ph, cr, tier)

            added = False
            for _k, (ph, cr, _t) in chosen.items():
                cur.execute(
                    """INSERT OR REPLACE INTO weapon_perks
                       (weapon_hash,column_index,column_kind,plug_hash,currently_can_roll,is_curated)
                       VALUES (?,?,?,?,?,?)""",
                    (item_hash, col_idx, kind, ph, 1 if cr else 0, 1 if ph == curated else 0),
                )
                added = True
            if added:
                col_idx += 1

        n_weapons += 1
        if limit and n_weapons >= limit:
            break

    cur.execute(
        "INSERT OR REPLACE INTO manifest_meta (id,version,ingested_at,locale,source) VALUES (1,?,?,?,?)",
        (version, datetime.now(timezone.utc).isoformat(), locale, "manifest"),
    )
    conn.commit()
    conn.close()
    print(f"완료: {n_weapons} 무기 적재 (version={version}) -> {config.DB_PATH}")


def main():
    ap = argparse.ArgumentParser(description="Bungie 매니페스트 적재기")
    ap.add_argument("--force", action="store_true", help="version 동일해도 강제 재적재")
    ap.add_argument("--limit", type=int, default=0, help="무기 N개만 적재(개발용)")
    args = ap.parse_args()
    ingest(force=args.force, limit=args.limit)


if __name__ == "__main__":
    main()
