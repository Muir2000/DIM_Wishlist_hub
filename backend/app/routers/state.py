"""사용자별 빌더 상태(위시리스트 롤 + 활성 프로필) 영속 — 로그인 필수.

상태 JSON 형태(클라이언트 소유): {rolls, title, description, activeProfileId}.
서버는 내용을 해석하지 않고 사용자(membership)별 1행으로 그대로 보관/반환한다.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from .. import repo
from ..db import get_conn
from ..session import require_membership

router = APIRouter(tags=["user-state"])

_EMPTY: Dict[str, Any] = {"rolls": [], "title": "", "description": "", "activeProfileId": None}


@router.get("/me/state")
def get_state(conn: sqlite3.Connection = Depends(get_conn),
              me: str = Depends(require_membership)) -> Dict[str, Any]:
    row = repo.get_user_state(conn, me)
    if not row or not row["json"]:
        return dict(_EMPTY)
    try:
        return json.loads(row["json"])
    except (ValueError, TypeError):
        return dict(_EMPTY)


@router.put("/me/state")
def put_state(state: Dict[str, Any] = Body(...),
              conn: sqlite3.Connection = Depends(get_conn),
              me: str = Depends(require_membership)) -> Dict[str, bool]:
    now = datetime.now(timezone.utc).isoformat()
    repo.upsert_user_state(conn, me, json.dumps(state), now)
    return {"ok": True}
