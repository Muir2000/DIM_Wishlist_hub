"""커뮤니티 메타 대시보드 / 퍽 인기도."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import labels, repo, serialize
from ..db import get_conn

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/top-weapons")
def top_weapons(
    limit: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_conn),
) -> List[Dict[str, Any]]:
    rows = repo.top_weapons(conn, limit=limit)
    out = []
    for r in rows:
        out.append({
            "item_hash": r["item_hash"],
            "name": r["name_ko"] or r["name_en"],
            "name_en": r["name_en"],
            "icon": serialize.icon_url(r["icon"]),
            "type_label": labels.weapon_type_label(r["weapon_subtype"]),
            "damage_label": labels.DAMAGE_KO.get(r["default_damage_type"]),
            "tier_label": labels.TIER_KO.get(r["tier"]),
            "total": r["total"],
        })
    return out


@router.get("/weapon/{item_hash}/perk-popularity")
def perk_popularity(item_hash: int, conn: sqlite3.Connection = Depends(get_conn)):
    """열별 퍽 인기도(인기도 막대용)."""
    if not repo.get_weapon(conn, item_hash):
        raise HTTPException(status_code=404, detail="무기를 찾을 수 없습니다.")
    by_col = repo.perk_popularity_by_column(conn, item_hash)
    result: Dict[str, Any] = {"item_hash": item_hash, "columns": {}}
    for col, perks in by_col.items():
        result["columns"][str(col)] = [
            {"plug_hash": ph, "count": cnt} for ph, cnt in sorted(perks.items(), key=lambda x: -x[1])
        ]
    return result
