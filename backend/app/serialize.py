"""DB Row -> Pydantic 모델 직렬화 헬퍼."""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from . import config, labels, repo, seasons
from .models import ColumnOut, PerkOut, WeaponDetail, WeaponSummary


def icon_url(rel: Optional[str]) -> Optional[str]:
    if not rel:
        return None
    if rel.startswith("http"):
        return rel
    return config.BUNGIE_ROOT + rel


def _col(row: sqlite3.Row, key: str, default=None):
    """row 에 컬럼이 있으면 값을, 없으면 default (구버전 DB/쿼리 안전)."""
    try:
        return row[key] if key in row.keys() else default
    except (IndexError, KeyError):
        return default


def weapon_summary(row: sqlite3.Row) -> WeaponSummary:
    s_num, s_name = seasons.season_for_watermark(row["watermark"])  # 원본 경로로 조회
    return WeaponSummary(
        item_hash=row["item_hash"],
        name=row["name_ko"] or row["name_en"] or str(row["item_hash"]),
        name_en=row["name_en"],
        icon=icon_url(row["icon"]),
        watermark=icon_url(row["watermark"]),
        season_number=s_num,
        season_name=s_name,
        season_name_en=seasons.season_name(s_num, "en"),
        tier=row["tier"],
        tier_label=labels.TIER_KO.get(row["tier"]),
        weapon_subtype=row["weapon_subtype"],
        type_label=labels.weapon_type_label(row["weapon_subtype"]),
        slot=row["slot"],
        default_damage_type=row["default_damage_type"],
        damage_label=labels.DAMAGE_KO.get(row["default_damage_type"]),
        variant_count=int(_col(row, "variant_count", 1) or 1),
        has_holofoil=bool(_col(row, "has_holofoil", 0)),
        has_adept=bool(_col(row, "has_adept", 0)),
        is_holofoil=bool(_col(row, "is_holofoil", 0)),
        season_count=int(_col(row, "season_count", 1) or 1),
    )


def weapon_detail(conn: sqlite3.Connection, row: sqlite3.Row) -> WeaponDetail:
    summary = weapon_summary(row)
    perk_rows = repo.get_weapon_perk_rows(conn, row["item_hash"])
    pop = repo.perk_popularity_by_column(conn, row["item_hash"])
    perk_stat_map = repo.all_perk_stats(conn, row["item_hash"])

    cols: Dict[int, ColumnOut] = {}
    for pr in perk_rows:
        idx = pr["column_index"]
        if idx not in cols:
            cols[idx] = ColumnOut(
                index=idx,
                kind=pr["column_kind"] or "trait",
                label=labels.column_label(pr["column_kind"], idx),
                perks=[],
            )
        cols[idx].perks.append(
            PerkOut(
                plug_hash=pr["plug_hash"],
                name=pr["name_ko"] or pr["name_en"] or str(pr["plug_hash"]),
                name_en=pr["name_en"],
                description=pr["description_ko"] or None,
                description_en=pr["description_en"] or None,
                icon=icon_url(pr["icon"]),
                plug_category=pr["plug_category"],
                currently_can_roll=bool(pr["currently_can_roll"]),
                is_curated=bool(pr["is_curated"]),
                is_enhanced=bool(pr["is_enhanced"]),
                popularity=pop.get(idx, {}).get(pr["plug_hash"], 0),
                stats=perk_stat_map.get(pr["plug_hash"]) or None,
            )
        )

    ordered: List[ColumnOut] = [cols[i] for i in sorted(cols.keys())]
    data = summary.model_dump()
    data["stats"] = repo.weapon_stats(conn, row["item_hash"]) or None

    # 변형 그룹 정보(상세는 get_weapon 의 단일 row 라 윈도우 집계가 없음 → 직접 조회)
    siblings = repo.variant_siblings(conn, row["item_hash"])
    data["variant_count"] = len(siblings) + 1
    data["season_count"] = repo.season_count(conn, row["item_hash"])
    if siblings:
        placeholders = ",".join("?" * len(siblings))
        agg = conn.execute(
            f"SELECT MAX(COALESCE(is_holofoil,0)) h, MAX(COALESCE(is_adept,0)) a "
            f"FROM weapons WHERE item_hash IN ({placeholders})",
            siblings,
        ).fetchone()
        data["has_holofoil"] = bool((agg["h"] if agg else 0) or data.get("is_holofoil"))
        data["has_adept"] = bool((agg["a"] if agg else 0) or _col(row, "is_adept", 0))
    return WeaponDetail(**data, columns=ordered)
