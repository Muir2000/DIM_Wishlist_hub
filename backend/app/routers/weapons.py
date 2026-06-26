"""무기 검색 / 상세 (퍽 풀 + 인기도 + 스탯) + 퍽/스탯 메타."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import labels, query as query_lang, repo, seasons, serialize
from ..db import get_conn
from ..models import WeaponDetail, WeaponSummary

router = APIRouter(tags=["weapons"])


def _csv_ints(s: Optional[str]) -> List[int]:
    return [int(x) for x in (s or "").split(",") if x.strip().lstrip("-").isdigit()]


def _csv_strs(s: Optional[str]) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _safe_float(v: str):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_stat_filters(stat_min: List[str], stat_max: List[str]) -> Dict[str, tuple]:
    """['handling:50', ...] -> {'handling': (50, 1e9)}. 잘못된 값은 무시(500 방지)."""
    filt: Dict[str, list] = {}
    for item in stat_min or []:
        if ":" in item:
            k, v = item.split(":", 1)
            fv = _safe_float(v)
            if fv is not None:
                filt.setdefault(k.strip(), [0.0, 1e9])[0] = fv
    for item in stat_max or []:
        if ":" in item:
            k, v = item.split(":", 1)
            fv = _safe_float(v)
            if fv is not None:
                filt.setdefault(k.strip(), [0.0, 1e9])[1] = fv
    return {k: (lo, hi) for k, (lo, hi) in filt.items()}


def search_params(
    q: Optional[str] = Query(None, description="이름 검색(ko/en)"),
    # 다중 선택(쉼표 구분) — 같은 카테고리 내 OR, 카테고리 간 AND
    subtypes: Optional[str] = Query(None, description="무기 종류(itemSubType) CSV, 예: 9,14"),
    tiers: Optional[str] = Query(None, description="등급 CSV: 5=전설,6=경이"),
    damages: Optional[str] = Query(None, description="속성 CSV: Kinetic,Arc,Solar,Void,Stasis,Strand"),
    slots: Optional[str] = Query(None, description="슬롯 CSV: Kinetic,Energy,Power"),
    ammo: Optional[str] = Query(None, description="탄약 CSV: 1=주무기,2=특수,3=강력"),
    frames: Optional[str] = Query(None, description="프레임(아키타입) 이름 CSV"),
    origins: Optional[str] = Query(None, description="기원 특성 이름 CSV(보유)"),
    seasons_q: Optional[str] = Query(None, alias="seasons", description="시즌 번호 CSV, 예: 5,23"),
    perk_exclude: Optional[str] = Query(None, description="제외할 plug_hash CSV(보유 시 제외)"),
    perkname: List[str] = Query(default=[], description="퍽 이름 반복(각각 OR 해시, 이름 간 AND)"),
    query: Optional[str] = Query(None, description="DIM식 텍스트 쿼리 (is:/perkname:/stat:>=/season:/and·or·not·())"),
    # 하위호환: 단수 파라미터도 허용
    subtype: Optional[int] = Query(None, description="(구) 단일 무기 종류"),
    tier: Optional[int] = Query(None, description="(구) 단일 등급"),
    damage: Optional[str] = Query(None, description="(구) 단일 속성"),
    perks: Optional[str] = Query(None, description="쉼표 구분 plug_hash, 모두 보유(AND)"),
    stat_min: List[str] = Query(default=[], description="'key:value' 반복 (예: handling:50)"),
    stat_max: List[str] = Query(default=[], description="'key:value' 반복 (예: recoil:20)"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    """검색/카운트 공용 — 쿼리 파라미터를 search_weapons kwargs 로 파싱(limit 제외)."""
    name_groups = [repo.resolve_perk_name_hashes(conn, nm) for nm in (perkname or []) if nm.strip()]
    name_groups = [g for g in name_groups if g]
    try:
        extra_where, extra_params = query_lang.compile_query(query or "")
    except query_lang.QueryError as e:
        raise HTTPException(status_code=400, detail=f"검색 쿼리 오류: {e}")
    return {
        "q": q,
        "subtypes": (_csv_ints(subtypes) or ([subtype] if subtype is not None else [])) or None,
        "tiers": (_csv_ints(tiers) or ([tier] if tier is not None else [])) or None,
        "damage_types": (_csv_strs(damages) or ([damage] if damage else [])) or None,
        "slots": _csv_strs(slots) or None,
        "ammo_types": _csv_ints(ammo) or None,
        "frames": _csv_strs(frames) or None,
        "origin_names": _csv_strs(origins) or None,
        "season_nums": _csv_ints(seasons_q) or None,
        "perk_hashes": [int(p) for p in (perks or "").split(",") if p.strip()] or None,
        "perk_any_groups": name_groups or None,
        "perk_excludes": _csv_ints(perk_exclude) or None,
        "stat_filters": _parse_stat_filters(stat_min, stat_max) or None,
        "extra_where": extra_where or None,
        "extra_params": extra_params,
    }


@router.get("/weapons", response_model=List[WeaponSummary])
def list_weapons(
    params: dict = Depends(search_params),
    limit: int = Query(50, ge=1, le=200),
    conn: sqlite3.Connection = Depends(get_conn),
):
    rows = repo.search_weapons(conn, limit=limit, **params)
    return [serialize.weapon_summary(r) for r in rows]


@router.get("/weapons/count", tags=["weapons"])
def count_weapons(
    params: dict = Depends(search_params),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, int]:
    """현재 필터/검색에 매칭되는 무기(시즌 그룹) 총 건수. LIMIT 무관."""
    return {"count": repo.search_weapons(conn, count_only=True, **params)}


@router.get("/search/help", tags=["weapons"])
def search_help() -> Dict[str, Any]:
    """텍스트 쿼리 지원 토큰·예시(프론트 치트시트)."""
    return query_lang.HELP


@router.get("/filters", tags=["weapons"])
def filter_facets(
    params: dict = Depends(search_params),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """카테고리별 필터 선택지 + 갯수 — **현재 검색/필터 결과 기준(컨텍스트 인지)**.
    각 카테고리는 자기 필터를 제외하고 계산해 OR 다중선택을 유지(예: '폭발 용광로' → 물리(3)/파동 소총(3))."""
    fc = repo.contextual_facets(conn, params)
    dm, st, ti, sl, am, fr = fc["elements"], fc["types"], fc["tiers"], fc["slots"], fc["ammo"], fc["frames"]
    fmap = repo.frame_name_map(conn)   # 프레임 한국어→영어(영어 모드 라벨용)
    DMG_ORDER = ["Kinetic", "Arc", "Solar", "Void", "Stasis", "Strand"]
    return {
        "elements": [
            {"value": k, "label": labels.DAMAGE_KO.get(k, k), "count": dm[k]}
            for k in DMG_ORDER if k in dm
        ] + [
            {"value": k, "label": labels.DAMAGE_KO.get(k, k), "count": v}
            for k, v in dm.items() if k not in DMG_ORDER
        ],
        "types": sorted(
            [{"value": k, "label": labels.WEAPON_SUBTYPE_KO.get(k, str(k)), "count": v}
             for k, v in st.items()],
            key=lambda x: -x["count"],
        ),
        "tiers": [
            {"value": k, "label": labels.TIER_KO.get(k, str(k)), "count": ti[k]}
            for k in (6, 5) if k in ti
        ],
        "slots": [
            {"value": k, "label": labels.SLOT_KO.get(k, k), "count": sl[k]}
            for k in ("Kinetic", "Energy", "Power") if k in sl
        ],
        "ammo": [
            {"value": k, "label": labels.AMMO_KO.get(k, str(k)), "count": am[k]}
            for k in (1, 2, 3) if k in am
        ],
        "frames": sorted(
            [{"value": k, "label": k, "label_en": fmap.get(k), "count": v} for k, v in fr.items() if k],
            key=lambda x: -x["count"],
        ),
        "origins": [
            {"value": r["v"], "label": r["v"], "label_en": r["v_en"], "count": r["c"]}
            for r in fc["origins"]
        ],
        "seasons": sorted(
            [{"value": num,
              "label": f"S{num} · {seasons.season_name(num) or ''}".strip(" ·"),
              "label_en": f"S{num} · {seasons.season_name(num, 'en') or ''}".strip(" ·"),
              "count": cnt}
             for num, cnt in fc["seasons"].items()],
            key=lambda x: -x["value"],
        ),
    }


@router.get("/weapons/{item_hash}", response_model=WeaponDetail)
def weapon_detail(item_hash: int, conn: sqlite3.Connection = Depends(get_conn)):
    row = repo.get_weapon(conn, item_hash)
    if not row:
        raise HTTPException(status_code=404, detail="무기를 찾을 수 없습니다.")
    return serialize.weapon_detail(conn, row)


@router.get("/perks", tags=["weapons"])
def search_perks(
    q: str = Query(..., min_length=1, description="퍽 이름 검색(ko/en)"),
    limit: int = Query(20, ge=1, le=50),
    conn: sqlite3.Connection = Depends(get_conn),
) -> List[Dict[str, Any]]:
    rows = repo.search_perks(conn, q, limit=limit)
    return [{
        "plug_hash": r["plug_hash"],
        "name": r["name_ko"] or r["name_en"],
        "name_en": r["name_en"],
        "icon": serialize.icon_url(r["icon"]),
        "plug_category": r["plug_category"],
    } for r in rows]


@router.get("/stat-defs", tags=["weapons"])
def stat_definitions(conn: sqlite3.Connection = Depends(get_conn)) -> List[Dict[str, Any]]:
    return [{
        "stat_hash": r["stat_hash"], "key": r["key"],
        "name": r["name_ko"] or r["name_en"], "name_en": r["name_en"],
    } for r in repo.stat_defs(conn)]
