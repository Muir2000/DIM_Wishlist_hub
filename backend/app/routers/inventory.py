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
from fastapi import APIRouter, Body, Depends, HTTPException, Query

from .. import config, labels, repo, scoring, serialize
from ..compiler import RollRequest, compile_wishlist
from ..db import get_conn
from ..models import CleanupItem, InventoryPerk, InventoryStatus, ScoringProfile
from .auth import access_token, oauth_configured

router = APIRouter(tags=["inventory (고도화)"])

PROFILE_COMPONENTS = "102,201,205,300,304,305"


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
def me_status(conn: sqlite3.Connection = Depends(get_conn)):
    tok = repo.get_token(conn)
    inv = repo.get_inventory(conn, tok["membership_id"]) if tok else []
    synced = inv[0]["synced_at"] if inv else None
    return InventoryStatus(
        connected=bool(tok),
        membership_id=tok["membership_id"] if tok else None,
        item_count=len(inv),
        synced_at=synced,
        oauth_configured=oauth_configured(),
        login_url="/api/auth/bungie/login" if oauth_configured() else None,
    )


@router.post("/me/sync", response_model=InventoryStatus)
def me_sync(conn: sqlite3.Connection = Depends(get_conn)):
    if not oauth_configured():
        raise HTTPException(status_code=501, detail="Bungie OAuth 미설정 (.env 의 CLIENT_ID/SECRET).")
    tok = access_token(conn)
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
    return me_status(conn)


@router.post("/me/demo-inventory", response_model=InventoryStatus)
def me_demo_inventory(conn: sqlite3.Connection = Depends(get_conn)):
    """OAuth 없이 정리 UI 를 체험하기 위한 합성 창고(시드 무기 기반)."""
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
    repo.replace_inventory(conn, "DEMO", rows)
    return InventoryStatus(connected=True, membership_id="DEMO", item_count=len(rows),
                           synced_at=now, oauth_configured=oauth_configured(),
                           login_url="/api/auth/bungie/login" if oauth_configured() else None)


def _score_inventory(conn, profile: Optional[dict], context: Optional[dict]) -> List[CleanupItem]:
    tok = repo.get_token(conn)
    membership = tok["membership_id"] if tok else None
    base_map = repo.enhanced_base_map(conn)  # 강화 퍽 → 기본 퍽
    out: List[CleanupItem] = []
    for row in repo.get_inventory(conn, membership):
        plugs = json.loads(row["plug_hashes"] or "[]")
        # 강화 퍽은 기본 퍽으로 정규화(풀은 base 만 보관)
        plugs = [base_map.get(p, p) for p in plugs]
        stats = json.loads(row["stats"] or "{}")
        w = repo.get_weapon(conn, row["item_hash"])
        if not w:
            continue
        # 인스턴스 퍽 중 이 무기의 랜덤롤 퍽(weapon_perks)만 추림 → 점수/트래시리스트에 사용
        known = {wp["plug_hash"] for wp in conn.execute(
            "SELECT plug_hash FROM weapon_perks WHERE weapon_hash = ?", (row["item_hash"],)).fetchall()}
        roll_perks = [p for p in plugs if p in known]
        res = scoring.score_roll(conn, row["item_hash"], roll_perks, profile,
                                 stats=stats or None, context=context)
        perk_names = []
        for ph in roll_perks:
            pr = conn.execute("SELECT name_ko, name_en FROM perks WHERE plug_hash = ?", (ph,)).fetchone()
            perk_names.append(InventoryPerk(
                plug_hash=ph,
                name=(pr["name_ko"] or pr["name_en"]) if pr else None,
                name_en=pr["name_en"] if pr else None,
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


@router.post("/me/cleanup", response_model=List[CleanupItem])
def me_cleanup(
    profile: Optional[ScoringProfile] = Body(default=None),
    wishlist_rolls: List[dict] = Body(default=[]),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """창고 무기를 점수순(낮은 순=정리 후보 우선)으로 채점."""
    ctx = scoring.derive_context(conn, wishlist_rolls)
    return _score_inventory(conn, profile.model_dump() if profile else None, ctx)


@router.post("/me/export-trashlist")
def me_export_trashlist(
    profile: Optional[ScoringProfile] = Body(default=None),
    wishlist_rolls: List[dict] = Body(default=[]),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Dict[str, Any]:
    """정리 후보(trash) 롤들을 DIM 트래시리스트(.txt)로. compiler 재사용."""
    ctx = scoring.derive_context(conn, wishlist_rolls)
    items = _score_inventory(conn, profile.model_dump() if profile else None, ctx)
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
