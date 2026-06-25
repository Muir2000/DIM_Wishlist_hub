"""위시리스트 컴파일 / 내보내기."""
from __future__ import annotations

import re
import sqlite3
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException

from .. import db, labels, repo, serialize
from ..compiler import CompileError, RollRequest, compile_roll, compile_wishlist, parse_wishlist
from ..db import get_conn
from ..models import (
    CompileOut, CompileRollIn, ExportIn, ExportOut,
    ImportedRoll, ImportIn, ImportOut,
)

router = APIRouter(tags=["wishlist"])


def _to_roll_request(
    item: CompileRollIn,
    conn: sqlite3.Connection = None,
    expand_variants: bool = True,
) -> RollRequest:
    cols: Dict[int, List[int]] = {}
    for k, v in (item.columns or {}).items():
        try:
            cols[int(k)] = list(v)
        except (TypeError, ValueError):
            continue

    variant_hashes: List[int] = []
    variant_pools: Dict[int, set] = {}
    # 복각/홀로포일 변형까지 자동 커버 — 같은 그룹의 모든 hash 에 같은 롤을 emit.
    if conn is not None and expand_variants and not item.wildcard and item.weapon_hash:
        for vh in repo.variant_siblings(conn, item.weapon_hash):
            variant_hashes.append(vh)
            variant_pools[vh] = repo.perk_pool(conn, vh)

    return RollRequest(
        weapon_hash=item.weapon_hash,
        columns=cols,
        wildcard=item.wildcard,
        trash=item.trash,
        notes=item.notes or "",
        tags=item.tags or [],
        comment=item.comment or "",
        variant_hashes=variant_hashes,
        variant_pools=variant_pools,
    )


def _slugify(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", text).strip("-")
    return text or "wishlist"


@router.post("/compile", response_model=CompileOut)
def compile_single(item: CompileRollIn, conn: sqlite3.Connection = Depends(get_conn)):
    """단일 롤 -> DIM 줄 배열(다중퍼크 자동 전개 + 변형 무기 확장) 미리보기."""
    base_map = repo.enhanced_base_map(conn)
    try:
        lines = compile_roll(_to_roll_request(item, conn), base_map=base_map)
    except CompileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CompileOut(lines=lines, line_count=len(lines))


@router.post("/export", response_model=ExportOut)
def export_wishlist(payload: ExportIn, conn: sqlite3.Connection = Depends(get_conn)):
    """여러 롤 -> 완성된 위시리스트 파일 본문(.txt)."""
    base_map = repo.enhanced_base_map(conn)
    rolls = [_to_roll_request(r, conn) for r in payload.rolls]
    try:
        content = compile_wishlist(
            rolls, title=payload.title, description=payload.description, base_map=base_map
        )
    except CompileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    line_count = sum(1 for ln in content.splitlines() if ln.startswith("dimwishlist:"))

    _, source, _ = db.active_info()
    warning = None
    if source == "seed":
        warning = (
            "현재 샘플(seed) 데이터로 동작 중입니다. 이 .txt 의 퍼크 해시는 합성값이라 "
            "DIM 에서 실제 매칭되지 않습니다. 실사용하려면 Bungie 매니페스트를 적재하세요."
        )

    filename = f"{_slugify(payload.title or 'dim-wishlist')}.txt"
    return ExportOut(
        filename=filename,
        content=content,
        line_count=line_count,
        roll_count=len(rolls),
        data_source=source,
        warning=warning,
    )


@router.post("/import-wishlist", response_model=ImportOut)
def import_wishlist(payload: ImportIn, conn: sqlite3.Connection = Depends(get_conn)):
    """외부 DIM 위시리스트 .txt → 빌더 리스트에 넣을 수 있는 롤 목록으로 변환.

    `// 무기이름` 블록의 여러 줄(카르테시안 전개)을 무기별로 합쳐(퍼크 합집합) 멀티선택 롤로 복원하고,
    각 퍼크를 그 무기의 실제 열로 매핑한다. DB 에 없는 무기/와일드카드는 건너뛴다.
    """
    parsed = parse_wishlist(payload.text or "")
    base_map = repo.enhanced_base_map(conn)
    out: List[ImportedRoll] = []
    imported = unknown = wildcard = 0

    for r in parsed["rolls"]:
        if r["wildcard"]:
            wildcard += 1
            continue
        w = repo.get_weapon(conn, r["item_hash"])
        if not w:
            unknown += 1
            continue
        colmap = repo.weapon_perk_columns(conn, r["item_hash"])
        columns: Dict[str, List[int]] = {}
        for ph in r["perks"]:
            bp = base_map.get(ph, ph)            # 강화 → base 정규화
            ci = colmap.get(bp)
            if ci is None:
                continue                          # 이 무기 풀에 없는 퍼크는 제외
            columns.setdefault(str(ci), [])
            if bp not in columns[str(ci)]:
                columns[str(ci)].append(bp)

        wname = w["name_ko"] or w["name_en"] or str(r["item_hash"])
        item = CompileRollIn(
            weapon_hash=r["item_hash"], columns=columns, wildcard=False,
            trash=bool(r["trash"]), notes=r["notes"] or "", tags=[], comment=wname,
        )
        try:
            lines = compile_roll(_to_roll_request(item, conn), base_map=base_map)
        except CompileError:
            lines = []  # 조합 폭발 시 미리보기 줄만 생략(롤 자체는 가져옴)
        selected = [h for hs in columns.values() for h in hs]
        names = repo.perk_names(conn, selected)
        out.append(ImportedRoll(
            input=item,
            weapon_name=wname,
            perk_labels=[names.get(h, str(h)) for h in selected],
            lines=lines,
            type_label=labels.weapon_type_label(w["weapon_subtype"]),
            damage_type=w["default_damage_type"],
            tier=w["tier"],
        ))
        imported += 1

    return ImportOut(
        title=parsed["title"], description=parsed["description"], rolls=out,
        imported=imported, unknown_weapons=unknown, skipped_lines=parsed["skipped"], wildcard=wildcard,
    )
