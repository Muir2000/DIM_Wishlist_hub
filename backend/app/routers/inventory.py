"""인벤토리 가져오기 + 정리 (v2 Phase 3).

- /me/status        : 연동/동기화 상태
- /me/sync          : Bungie GetProfile → 창고 무기 스냅샷 (OAuth 필요)
- /me/cleanup       : 각 무기를 점수 프로필로 채점·분류 (정리 후보 판별)
- /me/export-trashlist : 정리 후보를 DIM 트래시리스트(.txt)로 (compiler 재사용)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from .. import config, labels, repo, scoring, serialize, session
from ..compiler import RollRequest, compile_wishlist
from ..db import get_conn
from ..models import CleanupItem, InventoryPerk, InventoryStatus, ScoringProfile
from ..session import require_membership
from .auth import access_token, oauth_configured

router = APIRouter(tags=["inventory (고도화)"])

PROFILE_COMPONENTS = "102,201,205,300,304,305"


def _inv_key(request: Request) -> str:
    """인벤토리 스코프 키: 로그인 멤버십, 비로그인은 공용 데모('DEMO')."""
    return session.current_membership(request) or "DEMO"


def _variant_hashes(conn, weapon_hash: int) -> set:
    """선택 무기와 같은 변형 그룹(복각/홀로포일/에이뎁트)의 item_hash 집합.
    보유 인스턴스가 다른 시즌 변형이어도 '이 무기 보유'로 인식하기 위함."""
    row = conn.execute("SELECT variant_group FROM weapons WHERE item_hash = ?", (weapon_hash,)).fetchone()
    vg = row["variant_group"] if row else None
    if not vg:
        return {weapon_hash}
    rows = conn.execute("SELECT item_hash FROM weapons WHERE variant_group = ?", (vg,)).fetchall()
    return {r["item_hash"] for r in rows} or {weapon_hash}


def _global_kind(conn, plug_hash) -> Optional[str]:
    """어느 무기에서든 이 퍽의 열종류(barrel/magazine/trait/origin). 선택 무기 풀에 없을 때 보조."""
    r = conn.execute(
        "SELECT column_kind FROM weapon_perks WHERE plug_hash = ? LIMIT 1", (plug_hash,)).fetchone()
    return r["column_kind"] if r else None


def _stat_hash_map(conn) -> Dict[int, str]:
    return {r["stat_hash"]: r["key"] for r in repo.stat_defs(conn)}


def _weapon_hashes(conn) -> set:
    return {r["item_hash"] for r in conn.execute("SELECT item_hash FROM weapons").fetchall()}


def _collect_items(resp: dict) -> List[dict]:
    R = resp.get("Response", {})
    items: List[dict] = list(R.get("profileInventory", {}).get("data", {}).get("items", []))
    for cdata in (R.get("characterInventories", {}).get("data", {}) or {}).values():
        items += cdata.get("items", [])
    for cdata in (R.get("characterEquipment", {}).get("data", {}) or {}).values():
        items += cdata.get("items", [])
    return items


@router.get("/me/status", response_model=InventoryStatus)
def me_status(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    mem = session.current_membership(request)
    inv = repo.get_inventory(conn, mem or "DEMO")
    synced = inv[0]["synced_at"] if inv else None
    return InventoryStatus(
        connected=bool(mem),                  # 로그인(세션) 여부
        membership_id=mem,
        item_count=len(inv),
        synced_at=synced,
        oauth_configured=oauth_configured(),
        login_url="/api/auth/bungie/login" if oauth_configured() else None,
    )


@router.post("/me/sync", response_model=InventoryStatus)
def me_sync(request: Request, conn: sqlite3.Connection = Depends(get_conn),
            me: str = Depends(require_membership)):
    if not oauth_configured():
        raise HTTPException(status_code=501, detail="Bungie OAuth 미설정 (.env 의 CLIENT_ID/SECRET).")
    tok = access_token(conn, me)
    if not tok:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다. /auth/bungie/login")

    url = (f"https://www.bungie.net/Platform/Destiny2/{tok['membership_type']}/Profile/"
           f"{tok['membership_id']}/?components={PROFILE_COMPONENTS}")
    headers = {"X-API-Key": config.BUNGIE_API_KEY, "Authorization": f"Bearer {tok['access_token']}"}
    with httpx.Client(timeout=60.0) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        resp = r.json()

    R = resp.get("Response", {})
    ic = R.get("itemComponents", {})
    instances = ic.get("instances", {}).get("data", {}) or {}
    stats_comp = ic.get("stats", {}).get("data", {}) or {}
    sockets_comp = ic.get("sockets", {}).get("data", {}) or {}

    weapon_hashes = _weapon_hashes(conn)
    stat_map = _stat_hash_map(conn)
    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for it in _collect_items(resp):
        iid = it.get("itemInstanceId")
        ih = it.get("itemHash")
        if not iid or ih not in weapon_hashes:
            continue
        plugs = [s["plugHash"] for s in sockets_comp.get(iid, {}).get("sockets", []) if s.get("plugHash")]
        st = {}
        for sh, sv in (stats_comp.get(iid, {}).get("stats", {}) or {}).items():
            key = stat_map.get(int(sh))
            if key:
                st[key] = sv.get("value")
        power = (instances.get(iid, {}).get("primaryStat", {}) or {}).get("value")
        rows.append((iid, ih, json.dumps(plugs), json.dumps(st), power, now))

    repo.replace_inventory(conn, tok["membership_id"], rows)
    return me_status(request, conn)


@router.post("/me/demo-inventory", response_model=InventoryStatus)
def me_demo_inventory(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    """OAuth 없이 정리 UI 를 체험하기 위한 합성 창고(시드 무기 기반). 비로그인=공용 DEMO."""
    mem = _inv_key(request)
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for w in conn.execute("SELECT item_hash FROM weapons").fetchall():
        wh = w["item_hash"]
        base = dict(repo.weapon_stats(conn, wh))
        by_col: Dict[int, list] = {}
        for c in conn.execute(
            "SELECT column_index, plug_hash FROM weapon_perks WHERE weapon_hash=? ORDER BY column_index, plug_hash",
            (wh,),
        ).fetchall():
            by_col.setdefault(c["column_index"], []).append(c["plug_hash"])
        good = [v[0] for v in by_col.values()]
        bad = [v[-1] for v in by_col.values()]
        for tag, perks, hmod in (("GOOD", good, 12), ("BAD", bad, -16)):
            st = dict(base)
            st["handling"] = st.get("handling", 50) + hmod
            rows.append((f"DEMO-{wh}-{tag}", wh, json.dumps(perks), json.dumps(st), 1800, now))
    repo.replace_inventory(conn, mem, rows)
    return InventoryStatus(connected=mem != "DEMO", membership_id=mem, item_count=len(rows),
                           synced_at=now, oauth_configured=oauth_configured(),
                           login_url="/api/auth/bungie/login" if oauth_configured() else None)


def _score_inventory(conn, membership: str, profile: Optional[dict], context: Optional[dict],
                     weapon_hashes: Optional[set] = None) -> List[CleanupItem]:
    base_map = repo.enhanced_base_map(conn)  # 강화 퍽 → 기본 퍽
    out: List[CleanupItem] = []
    for row in repo.get_inventory(conn, membership):
        if weapon_hashes is not None and row["item_hash"] not in weapon_hashes:
            continue  # 특정 무기(변형 그룹)만 — 빌더 보유 롤 표시용
        raw_plugs = json.loads(row["plug_hashes"] or "[]")
        norm_plugs = [base_map.get(p, p) for p in raw_plugs]  # 강화→기본 정규화(점수 계산용)
        stats = json.loads(row["stats"] or "{}")
        w = repo.get_weapon(conn, row["item_hash"])
        if not w:
            continue
        kind_map = {wp["plug_hash"]: wp["column_kind"] for wp in conn.execute(
            "SELECT plug_hash, column_kind FROM weapon_perks WHERE weapon_hash = ?",
            (row["item_hash"],)).fetchall()}
        # 점수: 이 무기 풀(weapon_perks)에 매칭되는 퍽만 사용
        score_perks = [p for p in norm_plugs if p in kind_map]
        res = scoring.score_roll(conn, row["item_hash"], score_perks, profile,
                                 stats=stats or None, context=context)
        # 표시: 장착된 실제 퍽 전부. perks 테이블에 있으면 롤 퍽(코스메틱/마스터워크/인트린식은
        # ingest 에서 제외되어 미존재). 강화 퍽도 원본 해시 그대로 보여준다(실제 장착 반영).
        perk_names = []
        seen = set()
        for ph in raw_plugs:
            if ph in seen:
                continue
            pr = conn.execute("SELECT name_ko, name_en, icon FROM perks WHERE plug_hash = ?", (ph,)).fetchone()
            if not pr:
                continue
            seen.add(ph)
            base = base_map.get(ph, ph)
            kind = kind_map.get(ph) or kind_map.get(base) or _global_kind(conn, base)
            perk_names.append(InventoryPerk(
                plug_hash=ph,
                name=(pr["name_ko"] or pr["name_en"]),
                name_en=pr["name_en"],
                icon=serialize.icon_url(pr["icon"]),
                column_kind=kind,
            ))
        out.append(CleanupItem(
            item_instance_id=row["item_instance_id"], item_hash=row["item_hash"],
            name=w["name_ko"] or w["name_en"] or str(row["item_hash"]),
            name_en=w["name_en"],
            icon=serialize.icon_url(w["icon"]),
            weapon_subtype=w["weapon_subtype"],
            type_label=labels.weapon_type_label(w["weapon_subtype"]),
            default_damage_type=w["default_damage_type"],
            damage_label=labels.DAMAGE_KO.get(w["default_damage_type"]),
            tier=w["tier"],
            power=row["power"], perks=perk_names, stats=stats,
            score=res["score"], classification=res["classification"],
        ))
    out.sort(key=lambda x: (x.score if x.score is not None else 0))
    return out


@router.get("/me/debug-rolls")
def me_debug_rolls(
    request: Request,
    weapon_hash: Optional[int] = Query(default=None, description="특정 무기만(없으면 보유 인스턴스 앞 8개)"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """진단용: 동기화된 원본 plug_hashes 와 perks/풀 매칭 상태를 그대로 노출.
    퍽이 하나만 나오는 원인이 (1) 동기화 미수집인지 (2) 매칭 누락인지 구분하기 위함.
    로그인 상태로 브라우저에서 열어 JSON 을 공유하면 진단 가능."""
    mem = session.current_membership(request)
    if not mem:
        return {"error": "not logged in"}
    base_map = repo.enhanced_base_map(conn)
    hashes = _variant_hashes(conn, weapon_hash) if weapon_hash else None
    out: List[Dict[str, Any]] = []
    for row in repo.get_inventory(conn, mem):
        if hashes is not None and row["item_hash"] not in hashes:
            continue
        raw = json.loads(row["plug_hashes"] or "[]")
        pool = {wp["plug_hash"]: wp["column_kind"] for wp in conn.execute(
            "SELECT plug_hash, column_kind FROM weapon_perks WHERE weapon_hash = ?",
            (row["item_hash"],)).fetchall()}
        plug_info = []
        for ph in raw:
            pr = conn.execute("SELECT name_ko, name_en, plug_category FROM perks WHERE plug_hash = ?",
                              (ph,)).fetchone()
            base = base_map.get(ph, ph)
            plug_info.append({
                "plug_hash": ph, "base": base,
                "name": (pr["name_ko"] or pr["name_en"]) if pr else None,
                "plug_category": pr["plug_category"] if pr else None,
                "in_perks_table": bool(pr),
                "in_weapon_pool": (ph in pool) or (base in pool),
            })
        out.append({
            "instance": row["item_instance_id"], "item_hash": row["item_hash"],
            "raw_plug_count": len(raw), "pool_size": len(pool), "plugs": plug_info,
        })
        if hashes is None and len(out) >= 8:
            break
    return {"membership": mem, "weapon_hashes": list(hashes) if hashes else None, "instances": out}


@router.post("/me/weapon-rolls", response_model=List[CleanupItem])
def me_weapon_rolls(
    request: Request,
    weapon_hash: int = Body(...),
    profile: Optional[ScoringProfile] = Body(default=None),
    wishlist_rolls: List[dict] = Body(default=[]),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """로그인 사용자가 보유한 해당 무기 인스턴스 + 퍽롤·점수(빌더 표시용).
    비로그인/미동기화면 빈 목록. 점수순(낮은 순=정리 후보 우선)."""
    mem = session.current_membership(request)
    if not mem:
        return []
    ctx = scoring.derive_context(conn, wishlist_rolls)
    return _score_inventory(conn, mem, profile.model_dump() if profile else None, ctx,
                            weapon_hashes=_variant_hashes(conn, weapon_hash))


@router.post("/me/cleanup", response_model=List[CleanupItem])
def me_cleanup(
    request: Request,
    profile: Optional[ScoringProfile] = Body(default=None),
    wishlist_rolls: List[dict] = Body(default=[]),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """창고 무기를 점수순(낮은 순=정리 후보 우선)으로 채점."""
    ctx = scoring.derive_context(conn, wishlist_rolls)
    return _score_inventory(conn, _inv_key(request), profile.model_dump() if profile else None, ctx)


@router.post("/me/export-trashlist")
def me_export_trashlist(
    request: Request,
    profile: Optional[ScoringProfile] = Body(default=None),
    wishlist_rolls: List[dict] = Body(default=[]),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """정리 후보(trash) 롤들을 DIM 트래시리스트(.txt)로. compiler 재사용."""
    ctx = scoring.derive_context(conn, wishlist_rolls)
    items = _score_inventory(conn, _inv_key(request), profile.model_dump() if profile else None, ctx)
    base_map = repo.enhanced_base_map(conn)
    rolls: List[RollRequest] = []
    for it in items:
        if it.classification != "trash":
            continue
        # 각 퍽을 별도 열에 넣어 AND 한 줄(item=-hash&perks=...)로 만든다
        cols = {idx: [p.plug_hash] for idx, p in enumerate(it.perks)}
        rolls.append(RollRequest(weapon_hash=it.item_hash, columns=cols, trash=True,
                                 notes="정리 후보", comment=it.name))
    content = compile_wishlist(rolls, title="정리 리스트 (트래시)", base_map=base_map)
    line_count = sum(1 for ln in content.splitlines() if ln.startswith("dimwishlist:"))
    return {"filename": "cleanup-trashlist.txt", "content": content,
            "trash_count": len(rolls), "line_count": line_count}
