"""점수화 프로필 CRUD + 롤 점수 산정 (v2 Phase 2).

프로필 JSON 이 곧 공유 단위(파일 내보내기/가져오기와 동일 포맷).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from .. import labels, repo, scoring
from ..compiler import parse_line
from ..db import get_conn
from ..models import (
    DerivedWeight,
    DeriveWeightsRequest,
    DeriveWeightsResult,
    ScoreRequest,
    ScoreResult,
    ScoringProfile,
)

router = APIRouter(tags=["scoring"])


def _row_to_profile(row: sqlite3.Row) -> ScoringProfile:
    data = json.loads(row["json"])
    data["id"] = row["id"]
    data["updated_at"] = row["updated_at"]
    return ScoringProfile(**data)


@router.get("/scoring-profiles", response_model=List[ScoringProfile])
def list_profiles(conn: sqlite3.Connection = Depends(get_conn)):
    return [_row_to_profile(r) for r in repo.list_profiles(conn)]


@router.get("/scoring-profiles/{profile_id}", response_model=ScoringProfile)
def get_profile(profile_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    row = repo.get_profile(conn, profile_id)
    if not row:
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다.")
    return _row_to_profile(row)


@router.post("/scoring-profiles", response_model=ScoringProfile)
def save_profile(profile: ScoringProfile, conn: sqlite3.Connection = Depends(get_conn)):
    pid = profile.id or uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    profile.id = pid
    profile.updated_at = now
    repo.upsert_profile(conn, pid, profile.name, profile.model_dump_json(), now)
    return profile


@router.delete("/scoring-profiles/{profile_id}")
def delete_profile(profile_id: str, conn: sqlite3.Connection = Depends(get_conn)):
    n = repo.delete_profile(conn, profile_id)
    if not n:
        raise HTTPException(status_code=404, detail="프로필을 찾을 수 없습니다.")
    return {"deleted": profile_id}


def _resolve_profile(req: ScoreRequest, conn: sqlite3.Connection) -> dict:
    if req.profile is not None:
        return req.profile.model_dump()
    if req.profile_id:
        row = repo.get_profile(conn, req.profile_id)
        if row:
            return json.loads(row["json"])
    return scoring.default_profile()


@router.post("/score", response_model=ScoreResult)
def score(req: ScoreRequest, conn: sqlite3.Connection = Depends(get_conn)):
    prof = _resolve_profile(req, conn)
    ctx = scoring.derive_context(conn, [r.model_dump() for r in req.wishlist_rolls])
    result = scoring.score_roll(conn, req.weapon_hash, req.perks, prof, context=ctx)
    return ScoreResult(**result)


@router.post("/score/perk-weights")
def perk_weights(req: ScoreRequest, conn: sqlite3.Connection = Depends(get_conn)) -> Dict[str, Any]:
    """무기의 **모든 퍽**에 대해 활성 프로필+위시리스트 기준 가중치를 반환(빌더 퍽별 점수 표시용).

    반환: weights(plug→가중치), has_signal, scale(배지 척도=50),
    그리고 열 비중 환산 표시용 max_possible·coverage·column_weights·kinds(plug→열종류).
    퍽의 이 무기 점수 기여(%) = column_weights[kind] * weight * 100 / max_possible.
    """
    prof_raw = _resolve_profile(req, conn)
    ctx = scoring.derive_context(conn, [r.model_dump() for r in req.wishlist_rolls])
    plug_cols, weapon_cols = scoring.weapon_columns(conn, req.weapon_hash)
    hashes = list(plug_cols.keys())
    weights, has_signal = scoring.perk_weight_map(conn, req.weapon_hash, hashes, prof_raw, context=ctx)

    prof = scoring.normalize_profile(prof_raw)
    col_w = prof["column_weights"]
    max_possible = sum(col_w.get(k, 0.0) for k in weapon_cols.values()) or 1.0
    cov, _present = scoring.coverage(conn, req.weapon_hash, prof_raw, context=ctx)
    return {
        "weights": {str(k): v for k, v in weights.items()},
        "has_signal": has_signal,
        "scale": scoring.PERK_POINT_SCALE,
        "max_possible": round(max_possible, 3),
        "coverage": round(cov, 3),
        "column_weights": col_w,
        "kinds": {str(p): kind for p, (_ci, kind) in plug_cols.items()},
    }


def _text_to_rolls(text: str):
    """DIM 위시리스트 텍스트 → 컨텍스트 도출용 롤(무기 해시 포함). (rolls, parsed_count)"""
    rolls = []
    n = 0
    for line in (text or "").splitlines():
        if not line.startswith("dimwishlist:"):
            continue
        p = parse_line(line)
        if not p or not p["perks"]:
            continue
        n += 1
        if p["is_wildcard"]:
            continue  # 와일드카드는 무기 컨텍스트가 없어 제외
        rolls.append({"weapon_hash": p["item_hash"], "columns": {"0": list(p["perks"])},
                      "trash": p["is_undesirable"]})
    return rolls, n


def _perk_name(conn, ph: int):
    r = conn.execute("SELECT name_ko, name_en FROM perks WHERE plug_hash = ?", (ph,)).fetchone()
    return (r["name_en"] or r["name_ko"]) if r else None


def _scope_label(conn, scope: str):
    kind, _, val = scope.partition(":")
    if kind == "type":
        return labels.weapon_type_label(int(val)), "type"
    if kind == "frame":
        r = conn.execute("SELECT frame FROM weapons WHERE frame_hash = ? AND frame IS NOT NULL LIMIT 1",
                         (int(val),)).fetchone()
        return (r["frame"] if r and r["frame"] else f"프레임 {val}"), "frame"
    if kind == "weapon":
        r = conn.execute("SELECT name_ko, name_en FROM weapons WHERE item_hash = ?", (int(val),)).fetchone()
        return ((r["name_en"] or r["name_ko"]) if r else val), "weapon"
    return scope, "other"


# kind 정렬 우선순위(표시용): 종류 → 프레임 → 개별 무기
_KIND_ORDER = {"type": 0, "frame": 1, "weapon": 2, "other": 3}


@router.post("/scoring/derive-weights")
def derive_weights(req: DeriveWeightsRequest, conn: sqlite3.Connection = Depends(get_conn)) -> Dict[str, Any]:
    """위시리스트(구조화 롤 또는 DIM 텍스트) → 컨텍스트별 퍽 가중치 + 조합 도출. 프로필 등록용."""
    if req.text:
        rolls, parsed = _text_to_rolls(req.text)
    else:
        rolls = [r.model_dump() for r in req.rolls]
        parsed = len(rolls)

    ctx = scoring.derive_context(conn, rolls)
    # 프로필에 바로 구울(bake) 구조 (JSON 키는 문자열)
    context_weights = {sc: {str(p): w for p, w in pm.items()} for sc, pm in ctx["weights"].items()}
    context_synergies = ctx["combos"]

    # 표시용: 컨텍스트별 그룹 + 이름
    contexts = []
    for sc in set(list(ctx["weights"].keys()) + list(ctx["combos"].keys())):
        label, kind = _scope_label(conn, sc)
        weights = [{"plug_hash": p, "weight": w, "name": _perk_name(conn, p)}
                   for p, w in sorted(ctx["weights"].get(sc, {}).items(), key=lambda x: -x[1])]
        combos = [{"perks": [{"plug_hash": h, "name": _perk_name(conn, h)} for h in c["perks"]],
                   "bonus": c["bonus"]} for c in ctx["combos"].get(sc, [])]
        contexts.append({"scope": sc, "label": label, "kind": kind, "weights": weights, "combos": combos})
    contexts.sort(key=lambda c: (_KIND_ORDER.get(c["kind"], 9), c["label"]))

    return {"rolls_parsed": parsed, "context_weights": context_weights,
            "context_synergies": context_synergies, "contexts": contexts}
