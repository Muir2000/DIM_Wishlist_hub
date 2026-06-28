"""DB 질의 헬퍼 (라우터를 얇게 유지)."""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from . import seasons


def _build_where(
    q=None, subtypes=None, tiers=None, damage_types=None, slots=None, ammo_types=None,
    frames=None, origin_names=None, season_nums=None, perk_hashes=None, perk_any_groups=None,
    perk_excludes=None, stat_filters=None, extra_where=None, extra_params=None,
):
    """필터 kwargs → (where_sql, params). search_weapons / 패싯 계산이 공유."""
    where = "WHERE w.redacted = 0"
    params: list = []
    if q:
        where += " AND (w.name_ko LIKE ? OR w.name_en LIKE ?)"
        like = f"%{q}%"
        params += [like, like]

    def _in(col, values, cast=lambda x: x):
        nonlocal where
        vals = [cast(v) for v in (values or []) if v is not None and v != ""]
        if vals:
            where += f" AND w.{col} IN ({','.join('?' * len(vals))})"
            params.extend(vals)

    _in("weapon_subtype", subtypes, int)
    _in("tier", tiers, int)
    _in("default_damage_type", damage_types)
    _in("slot", slots)
    _in("ammo_type", ammo_types, int)
    _in("frame", frames)

    def _ph(n):
        return ",".join("?" * n)

    origin_vals = [o for o in (origin_names or []) if o not in (None, "")]
    if origin_vals:
        where += (f" AND w.item_hash IN (SELECT wp.weapon_hash FROM weapon_perks wp "
                  f"JOIN perks p ON p.plug_hash = wp.plug_hash "
                  f"WHERE wp.column_kind = 'origin' AND p.name_ko IN ({_ph(len(origin_vals))}))")
        params += origin_vals

    season_vals = [int(s) for s in (season_nums or []) if s not in (None, "")]
    if season_vals:
        wms: list = []
        for n in season_vals:
            wms += seasons.watermarks_for_season(n)
        if wms:
            where += f" AND w.watermark IN ({_ph(len(wms))})"
            params += wms
        else:
            where += " AND 0"

    for ph in perk_hashes or []:
        where += " AND w.item_hash IN (SELECT weapon_hash FROM weapon_perks WHERE plug_hash = ?)"
        params.append(int(ph))

    for group in perk_any_groups or []:
        g = [int(h) for h in group if h not in (None, "")]
        if g:
            where += (f" AND w.item_hash IN (SELECT weapon_hash FROM weapon_perks "
                      f"WHERE plug_hash IN ({_ph(len(g))}))")
            params += g

    excl = [int(h) for h in (perk_excludes or []) if h not in (None, "")]
    if excl:
        where += (f" AND w.item_hash NOT IN (SELECT weapon_hash FROM weapon_perks "
                  f"WHERE plug_hash IN ({_ph(len(excl))}))")
        params += excl

    for stat_key, (lo, hi) in (stat_filters or {}).items():
        where += (" AND w.item_hash IN (SELECT weapon_hash FROM weapon_stats "
                  "WHERE stat_key = ? AND value >= ? AND value <= ?)")
        params += [stat_key, lo, hi]

    if extra_where:
        where += f" AND ({extra_where})"
        params += list(extra_params or [])
    return where, params


def search_weapons(
    conn: sqlite3.Connection,
    q: Optional[str] = None,
    subtypes: Optional[List[int]] = None,               # 무기 종류(OR)
    tiers: Optional[List[int]] = None,                  # 등급 5/6 (OR)
    damage_types: Optional[List[str]] = None,           # 속성(OR)
    slots: Optional[List[str]] = None,                  # 슬롯 Kinetic/Energy/Power (OR)
    ammo_types: Optional[List[int]] = None,             # 탄약 1/2/3 (OR)
    frames: Optional[List[str]] = None,                 # 프레임(아키타입) 이름(OR)
    origin_names: Optional[List[str]] = None,           # 기원 특성 이름(OR — 보유, 시즌별 해시 차이 흡수)
    season_nums: Optional[List[int]] = None,            # 시즌 번호(OR)
    perk_hashes: Optional[List[int]] = None,            # 이 퍽들을 모두 보유(AND)
    perk_any_groups: Optional[List[List[int]]] = None,  # 그룹 내 OR(이름→다중해시), 그룹 간 AND
    perk_excludes: Optional[List[int]] = None,          # 이 퍽 중 하나라도 보유 시 제외(NOT)
    stat_filters: Optional[Dict[str, tuple]] = None,    # {stat_key: (min, max)}
    extra_where: Optional[str] = None,                  # 텍스트 쿼리 컴파일 결과(Phase B)
    extra_params: Optional[list] = None,
    limit: int = 50,
    count_only: bool = False,                           # True 면 매칭 총 건수(int) 반환
):
    """검색 결과를 **시즌(변형) 단위**로 1개씩 접어서 반환.

    같은 무기라도 시즌(복각)마다 퍽 풀이 다르므로, (variant_group + watermark) = 시즌 으로
    묶는다. 같은 시즌의 홀로포일은 퍽 풀이 동일하므로 일반판과 한 행으로 병합된다(대표는
    비홀로포일 우선). 시즌이 다르면 같은 이름이라도 별도 행으로 나온다.

    각 행에 부착: variant_count(이 시즌의 무기 수=일반+홀로포일), has_holofoil/has_adept(이 시즌),
    season_count(이 무기의 총 시즌 수). 같은 카테고리 내 여러 값은 OR, 카테고리 간에는 AND.
    """
    where, params = _build_where(
        q=q, subtypes=subtypes, tiers=tiers, damage_types=damage_types, slots=slots,
        ammo_types=ammo_types, frames=frames, origin_names=origin_names, season_nums=season_nums,
        perk_hashes=perk_hashes, perk_any_groups=perk_any_groups, perk_excludes=perk_excludes,
        stat_filters=stat_filters, extra_where=extra_where, extra_params=extra_params,
    )

    # 시즌 키 = variant_group(없으면 item_hash) + watermark. 같은 시즌의 홀로포일은 병합됨.
    SEASON = "(COALESCE(w.variant_group, CAST(w.item_hash AS TEXT)) || '|' || COALESCE(w.watermark, ''))"
    VG = "COALESCE(w.variant_group, CAST(w.item_hash AS TEXT))"
    sql = f"""
    WITH wpc AS (SELECT weapon_hash, COUNT(*) AS c FROM weapon_perks GROUP BY weapon_hash),
    seasons AS (
      SELECT COALESCE(variant_group, CAST(item_hash AS TEXT)) AS vg,
             COUNT(DISTINCT COALESCE(watermark, '')) AS sc
      FROM weapons WHERE redacted = 0
      GROUP BY COALESCE(variant_group, CAST(item_hash AS TEXT))
    ),
    ranked AS (
      SELECT w.*, COALESCE(wpc.c, 0) AS pc, {VG} AS vg,
        ROW_NUMBER() OVER (
          PARTITION BY {SEASON}
          ORDER BY COALESCE(w.is_holofoil,0) ASC, COALESCE(wpc.c,0) DESC, w.item_hash
        ) AS rn,
        COUNT(*) OVER (PARTITION BY {SEASON}) AS variant_count,
        MAX(COALESCE(w.is_holofoil,0)) OVER (PARTITION BY {SEASON}) AS has_holofoil,
        MAX(COALESCE(w.is_adept,0)) OVER (PARTITION BY {SEASON}) AS has_adept
      FROM weapons w LEFT JOIN wpc ON wpc.weapon_hash = w.item_hash
      {where}
    )"""
    if count_only:
        # 매칭된 시즌-그룹(결과 행) 수 — LIMIT 무관 총 건수
        row = conn.execute(sql + " SELECT COUNT(*) AS c FROM ranked r WHERE r.rn = 1", params).fetchone()
        return int(row["c"]) if row else 0
    sql += """
    SELECT r.*, COALESCE(s.sc, 1) AS season_count
    FROM ranked r LEFT JOIN seasons s ON s.vg = r.vg
    WHERE r.rn = 1
    ORDER BY r.name_ko, r.pc DESC, r.item_hash
    LIMIT ?
    """
    params.append(limit)
    return conn.execute(sql, params).fetchall()


# ---- 컨텍스트 인지 패싯 (현재 검색/필터 결과 기준, 시즌 접기) ----
_FACET_SEASON = "(COALESCE(w.variant_group, CAST(w.item_hash AS TEXT)) || '|' || COALESCE(w.watermark, ''))"


def _facet_cte(where_sql: str) -> str:
    return f"""
    WITH wpc AS (SELECT weapon_hash, COUNT(*) c FROM weapon_perks GROUP BY weapon_hash),
    ranked AS (
      SELECT w.*, ROW_NUMBER() OVER (PARTITION BY {_FACET_SEASON}
        ORDER BY COALESCE(w.is_holofoil,0) ASC, COALESCE(wpc.c,0) DESC, w.item_hash) AS rn
      FROM weapons w LEFT JOIN wpc ON wpc.weapon_hash = w.item_hash
      {where_sql})"""


def _facet_by_col(conn, base: dict, exclude_key: str, col: str, extra_cond: str = "") -> Dict:
    """카테고리 패싯: 자기 필터(exclude_key)를 뺀 컨텍스트에서 col 별 시즌그룹 수."""
    where, params = _build_where(**{**base, exclude_key: None})
    sql = _facet_cte(where) + (
        f" SELECT {col} AS v, COUNT(*) AS c FROM ranked "
        f"WHERE rn=1 AND {col} IS NOT NULL AND {col} != 'None'{extra_cond} GROUP BY {col}"
    )
    return {r["v"]: r["c"] for r in conn.execute(sql, params).fetchall()}


def _facet_origins(conn, base: dict) -> List[sqlite3.Row]:
    where, params = _build_where(**{**base, "origin_names": None})
    sql = _facet_cte(where) + """
      SELECT p.name_ko AS v, MAX(p.name_en) AS v_en, COUNT(DISTINCT wp.weapon_hash) AS c
      FROM weapon_perks wp JOIN perks p ON p.plug_hash = wp.plug_hash
      WHERE wp.column_kind = 'origin' AND p.name_ko IS NOT NULL
        AND wp.weapon_hash IN (SELECT item_hash FROM ranked WHERE rn = 1)
      GROUP BY p.name_ko ORDER BY c DESC"""
    return conn.execute(sql, params).fetchall()


def frame_name_map(conn: sqlite3.Connection) -> Dict[str, str]:
    """프레임(아키타입) 한국어명 → 영어명 매핑(weapons.frame_en). 영어 모드 프레임 라벨용.

    frame_en 은 매니페스트 적재 시 채워진다(ingest). 컬럼이 없는 구버전 DB(미적재)에서는
    빈 매핑을 반환해 호출부가 한국어로 폴백하게 한다(graceful)."""
    try:
        rows = conn.execute(
            "SELECT frame AS ko, frame_en AS en FROM weapons "
            "WHERE frame IS NOT NULL AND frame != '' AND frame_en IS NOT NULL AND frame_en != ''"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}  # frame_en 컬럼 없음(재적재 전) → 한국어 폴백
    return {r["ko"]: r["en"] for r in rows if r["ko"] and r["en"]}


def _facet_seasons(conn, base: dict) -> Dict[int, int]:
    where, params = _build_where(**{**base, "season_nums": None})
    sql = _facet_cte(where) + " SELECT watermark AS v, COUNT(*) AS c FROM ranked WHERE rn=1 AND watermark IS NOT NULL GROUP BY watermark"
    out: Dict[int, int] = {}
    for r in conn.execute(sql, params).fetchall():
        n = seasons.season_number(r["v"])
        if n is not None:
            out[n] = out.get(n, 0) + r["c"]
    return out


def contextual_facets(conn: sqlite3.Connection, base: dict) -> dict:
    """현재 검색/필터(base) 기준, 각 카테고리의 가용 값 + 갯수(시즌그룹). 각 카테고리는 자기 필터 제외."""
    return {
        "elements": _facet_by_col(conn, base, "damage_types", "default_damage_type"),
        "types": _facet_by_col(conn, base, "subtypes", "weapon_subtype"),
        "tiers": _facet_by_col(conn, base, "tiers", "tier"),
        "slots": _facet_by_col(conn, base, "slots", "slot"),
        "ammo": _facet_by_col(conn, base, "ammo_types", "ammo_type"),
        "frames": _facet_by_col(conn, base, "frames", "frame", extra_cond=" AND tier = 5"),
        "origins": _facet_origins(conn, base),
        "seasons": _facet_seasons(conn, base),
    }


def facet_counts(conn: sqlite3.Connection, column: str) -> Dict:
    """검색 필터용 패싯: {값: 그룹 수}. 변형을 접어 distinct variant_group 으로 집계."""
    rows = conn.execute(
        f"""SELECT {column} AS v,
                  COUNT(DISTINCT COALESCE(variant_group, CAST(item_hash AS TEXT))) AS c
           FROM weapons
           WHERE redacted = 0 AND {column} IS NOT NULL AND {column} != 'None'
           GROUP BY {column}""",
    ).fetchall()
    return {r["v"]: r["c"] for r in rows}


def frame_facets(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """프레임(아키타입) 패싯 — 칩 노출용.

    경이(tier 6) 무기는 각자 고유 인트린식 프레임(1-of-1)을 가져 패싯이 폭증한다(전체 171개 중 139개).
    따라서 칩에는 **전설(tier 5) 무기에서 2개 이상 그룹이 공유하는 아키타입**만 노출한다(≈29개).
    검색 자체는 임의 프레임 이름으로 여전히 가능(이건 표시만 정리).
    """
    return conn.execute(
        """SELECT frame AS name,
                  COUNT(DISTINCT COALESCE(variant_group, CAST(item_hash AS TEXT))) AS c
           FROM weapons
           WHERE redacted = 0 AND tier = 5 AND frame IS NOT NULL AND frame != ''
           GROUP BY frame
           HAVING c >= 2
           ORDER BY c DESC""",
    ).fetchall()


def origin_facets(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """기원 특성 패싯: 이름별 (이 origin 을 가진) 무기 그룹 수. 이름 기준(시즌별 해시 통합)."""
    return conn.execute(
        """SELECT p.name_ko AS name,
                  COUNT(DISTINCT COALESCE(w.variant_group, CAST(w.item_hash AS TEXT))) AS c
           FROM weapon_perks wp
           JOIN perks p ON p.plug_hash = wp.plug_hash
           JOIN weapons w ON w.item_hash = wp.weapon_hash
           WHERE wp.column_kind = 'origin' AND w.redacted = 0 AND p.name_ko IS NOT NULL
           GROUP BY p.name_ko
           ORDER BY c DESC""",
    ).fetchall()


def season_facets(conn: sqlite3.Connection) -> Dict[int, int]:
    """시즌 패싯: {시즌번호: 무기 그룹 수}. watermark→시즌 매핑(seasons)으로 집계."""
    rows = conn.execute(
        "SELECT watermark, COALESCE(variant_group, CAST(item_hash AS TEXT)) AS vg "
        "FROM weapons WHERE redacted = 0 AND watermark IS NOT NULL"
    ).fetchall()
    groups_by_season: Dict[int, set] = {}
    for r in rows:
        num = seasons.season_number(r["watermark"])
        if num is not None:
            groups_by_season.setdefault(num, set()).add(r["vg"])
    return {num: len(vgs) for num, vgs in groups_by_season.items()}


def resolve_perk_name_hashes(conn: sqlite3.Connection, name: str) -> List[int]:
    """퍽 이름(부분일치) → 해당하는 모든 plug_hash. 이름 기반 perkname 필터용(시즌별 해시 OR)."""
    like = f"%{name}%"
    rows = conn.execute(
        "SELECT plug_hash FROM perks WHERE name_ko LIKE ? OR name_en LIKE ?",
        (like, like),
    ).fetchall()
    return [r["plug_hash"] for r in rows]


def variant_siblings(conn: sqlite3.Connection, item_hash: int) -> List[int]:
    """같은 변형 그룹(복각/홀로포일/에이뎁트)의 다른 무기 해시들(자기 자신 제외)."""
    row = conn.execute("SELECT variant_group FROM weapons WHERE item_hash = ?", (item_hash,)).fetchone()
    if not row or not row["variant_group"]:
        return []
    rows = conn.execute(
        "SELECT item_hash FROM weapons WHERE variant_group = ? AND item_hash != ? AND redacted = 0",
        (row["variant_group"], item_hash),
    ).fetchall()
    return [r["item_hash"] for r in rows]


def season_count(conn: sqlite3.Connection, item_hash: int) -> int:
    """이 무기(변형 그룹)의 총 시즌 수 = 서로 다른 watermark 개수."""
    row = conn.execute("SELECT variant_group FROM weapons WHERE item_hash = ?", (item_hash,)).fetchone()
    if not row or not row["variant_group"]:
        return 1
    r = conn.execute(
        "SELECT COUNT(DISTINCT COALESCE(watermark,'')) AS sc FROM weapons WHERE variant_group = ? AND redacted = 0",
        (row["variant_group"],),
    ).fetchone()
    return int(r["sc"]) if r and r["sc"] else 1


def weapon_perk_columns(conn: sqlite3.Connection, item_hash: int) -> Dict[int, int]:
    """{plug_hash: column_index} — 가져온 위시리스트 퍽을 올바른 열로 매핑."""
    return {r["plug_hash"]: r["column_index"] for r in conn.execute(
        "SELECT plug_hash, column_index FROM weapon_perks WHERE weapon_hash = ?", (item_hash,)).fetchall()}


def perk_names(conn: sqlite3.Connection, plug_hashes) -> Dict[int, str]:
    """plug_hash → 이름(ko 우선). 가져오기 라벨용."""
    hs = [int(h) for h in plug_hashes]
    if not hs:
        return {}
    ph = ",".join("?" * len(hs))
    return {r["plug_hash"]: (r["name_ko"] or r["name_en"] or str(r["plug_hash"]))
            for r in conn.execute(f"SELECT plug_hash, name_ko, name_en FROM perks WHERE plug_hash IN ({ph})", hs).fetchall()}


def perk_pool(conn: sqlite3.Connection, item_hash: int) -> set:
    """무기가 굴릴 수 있는 plug_hash 집합(변형별 emit 필터용)."""
    return {r["plug_hash"] for r in conn.execute(
        "SELECT plug_hash FROM weapon_perks WHERE weapon_hash = ?", (item_hash,)).fetchall()}


def weapon_stats(conn: sqlite3.Connection, item_hash: int) -> Dict[str, float]:
    rows = conn.execute(
        "SELECT stat_key, value FROM weapon_stats WHERE weapon_hash = ?", (item_hash,)
    ).fetchall()
    return {r["stat_key"]: r["value"] for r in rows}


def perk_stats(conn: sqlite3.Connection, plug_hash: int) -> Dict[str, float]:
    rows = conn.execute(
        "SELECT stat_key, value FROM perk_stats WHERE plug_hash = ?", (plug_hash,)
    ).fetchall()
    return {r["stat_key"]: r["value"] for r in rows}


def all_perk_stats(conn: sqlite3.Connection, item_hash: int) -> Dict[int, Dict[str, float]]:
    """무기에 등장하는 모든 퍽의 스탯 델타 {plug_hash: {stat_key: value}}."""
    rows = conn.execute(
        """SELECT ps.plug_hash, ps.stat_key, ps.value
           FROM perk_stats ps
           WHERE ps.plug_hash IN (SELECT plug_hash FROM weapon_perks WHERE weapon_hash = ?)""",
        (item_hash,),
    ).fetchall()
    out: Dict[int, Dict[str, float]] = {}
    for r in rows:
        out.setdefault(r["plug_hash"], {})[r["stat_key"]] = r["value"]
    return out


def stat_defs(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT stat_hash, key, name_ko, name_en FROM stat_defs").fetchall()


def search_perks(conn: sqlite3.Connection, q: str, limit: int = 20) -> List[sqlite3.Row]:
    like = f"%{q}%"
    return conn.execute(
        """SELECT plug_hash, name_ko, name_en, icon, plug_category
           FROM perks WHERE is_enhanced = 0 AND (name_ko LIKE ? OR name_en LIKE ?)
           GROUP BY name_ko
           ORDER BY name_ko LIMIT ?""",
        (like, like, limit),
    ).fetchall()


def get_weapon(conn: sqlite3.Connection, item_hash: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM weapons WHERE item_hash = ?", (item_hash,)
    ).fetchone()


def get_weapon_perk_rows(conn: sqlite3.Connection, item_hash: int) -> List[sqlite3.Row]:
    return conn.execute(
        """SELECT wp.column_index, wp.column_kind, wp.plug_hash,
                  wp.currently_can_roll, wp.is_curated,
                  p.name_ko, p.name_en, p.description_ko, p.description_en,
                  p.icon, p.plug_category, p.is_enhanced
           FROM weapon_perks wp
           JOIN perks p ON p.plug_hash = wp.plug_hash
           WHERE wp.weapon_hash = ?
           ORDER BY wp.column_index""",
        (item_hash,),
    ).fetchall()


def popularity_map(conn: sqlite3.Connection, item_hash: int) -> Dict[int, int]:
    """(plug_hash -> 총 count) 매핑. 열 무관 합산."""
    rows = conn.execute(
        "SELECT plug_hash, SUM(count) AS c FROM roll_stats WHERE weapon_hash = ? GROUP BY plug_hash",
        (item_hash,),
    ).fetchall()
    return {r["plug_hash"]: r["c"] for r in rows}


def perk_popularity_by_column(conn: sqlite3.Connection, item_hash: int) -> Dict[int, Dict[int, int]]:
    rows = conn.execute(
        """SELECT column_index, plug_hash, SUM(count) AS c
           FROM roll_stats WHERE weapon_hash = ?
           GROUP BY column_index, plug_hash""",
        (item_hash,),
    ).fetchall()
    out: Dict[int, Dict[int, int]] = {}
    for r in rows:
        out.setdefault(r["column_index"], {})[r["plug_hash"]] = r["c"]
    return out


def top_weapons(conn: sqlite3.Connection, limit: int = 20) -> List[sqlite3.Row]:
    return conn.execute(
        """SELECT w.item_hash, w.name_ko, w.name_en, w.icon, w.watermark,
                  w.tier, w.weapon_subtype, w.slot, w.default_damage_type,
                  COALESCE(SUM(rs.count), 0) AS total
           FROM weapons w
           LEFT JOIN roll_stats rs ON rs.weapon_hash = w.item_hash
           WHERE w.redacted = 0
           GROUP BY w.item_hash
           HAVING total > 0
           ORDER BY total DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()


def enhanced_base_map(conn: sqlite3.Connection) -> Dict[int, int]:
    """강화 퍽 -> 기본 퍽 해시 매핑 (컴파일 시 base 만 emit)."""
    rows = conn.execute(
        "SELECT plug_hash, base_plug_hash FROM perks WHERE is_enhanced = 1 AND base_plug_hash IS NOT NULL"
    ).fetchall()
    return {r["plug_hash"]: r["base_plug_hash"] for r in rows}


def weapons_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS c FROM weapons").fetchone()["c"]


# --- 점수화 프로필 (JSON blob 저장; owner=membership_id 로 사용자별 분리) ---
def list_profiles(conn: sqlite3.Connection, owner: Optional[str]) -> List[sqlite3.Row]:
    if not owner:
        return []  # 비로그인: 빈 목록(레거시 NULL-owner 전역 프로필 미노출)
    return conn.execute(
        "SELECT id, name, json, updated_at FROM scoring_profiles WHERE owner = ? ORDER BY updated_at DESC",
        (owner,),
    ).fetchall()


def get_profile(conn: sqlite3.Connection, profile_id: str, owner: Optional[str] = None) -> Optional[sqlite3.Row]:
    if owner:
        return conn.execute(
            "SELECT id, name, json, updated_at FROM scoring_profiles WHERE id = ? AND owner = ?",
            (profile_id, owner),
        ).fetchone()
    return conn.execute(
        "SELECT id, name, json, updated_at FROM scoring_profiles WHERE id = ?", (profile_id,)
    ).fetchone()


def upsert_profile(conn: sqlite3.Connection, profile_id: str, name: str, json_str: str,
                   owner: str, updated_at: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO scoring_profiles (id, name, json, owner, updated_at)
           VALUES (?,?,?,?,?)""",
        (profile_id, name, json_str, owner, updated_at),
    )
    conn.commit()


def delete_profile(conn: sqlite3.Connection, profile_id: str, owner: Optional[str] = None) -> int:
    if owner:
        cur = conn.execute("DELETE FROM scoring_profiles WHERE id = ? AND owner = ?", (profile_id, owner))
    else:
        cur = conn.execute("DELETE FROM scoring_profiles WHERE id = ?", (profile_id,))
    conn.commit()
    return cur.rowcount


# --- 사용자별 빌더 상태 (위시리스트 롤 + 활성 프로필) ---
def get_user_state(conn: sqlite3.Connection, owner: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT json, updated_at FROM user_state WHERE owner = ?", (owner,)
    ).fetchone()


def upsert_user_state(conn: sqlite3.Connection, owner: str, json_str: str, updated_at: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO user_state (owner, json, updated_at) VALUES (?,?,?)",
        (owner, json_str, updated_at),
    )
    conn.commit()


# --- OAuth 토큰 / 인벤토리 (v2 Phase 3) ---
def save_token(conn, membership_id, membership_type, access, refresh, expires_at, display_name=None) -> None:
    # display_name 미전달(리프레시 등) 시 기존 값 보존.
    conn.execute(
        """INSERT INTO oauth_tokens
           (membership_id, membership_type, access_token, refresh_token, expires_at, display_name)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(membership_id) DO UPDATE SET
             membership_type=excluded.membership_type,
             access_token=excluded.access_token,
             refresh_token=excluded.refresh_token,
             expires_at=excluded.expires_at,
             display_name=COALESCE(excluded.display_name, oauth_tokens.display_name)""",
        (membership_id, membership_type, access, refresh, expires_at, display_name),
    )
    conn.commit()


def get_token(conn, membership_id: Optional[str] = None) -> Optional[sqlite3.Row]:
    if membership_id:
        return conn.execute("SELECT * FROM oauth_tokens WHERE membership_id = ?", (membership_id,)).fetchone()
    return conn.execute("SELECT * FROM oauth_tokens ORDER BY rowid DESC LIMIT 1").fetchone()


def replace_inventory(conn, membership_id: str, items: list) -> None:
    """해당 멤버십의 인벤토리 스냅샷 교체.
    items: [(instance_id, item_hash, plug_json, stats_json, power, synced_at[, reusable_json])]"""
    conn.execute("DELETE FROM inventory_items WHERE membership_id = ?", (membership_id,))
    conn.executemany(
        """INSERT OR REPLACE INTO inventory_items
           (item_instance_id, membership_id, item_hash, plug_hashes, stats, power, synced_at, reusable_plugs)
           VALUES (?,?,?,?,?,?,?,?)""",
        [(it[0], membership_id, it[1], it[2], it[3], it[4], it[5],
          it[6] if len(it) > 6 else None) for it in items],
    )
    conn.commit()


def get_inventory(conn, membership_id: Optional[str] = None) -> List[sqlite3.Row]:
    if membership_id:
        return conn.execute("SELECT * FROM inventory_items WHERE membership_id = ?", (membership_id,)).fetchall()
    return conn.execute("SELECT * FROM inventory_items").fetchall()
