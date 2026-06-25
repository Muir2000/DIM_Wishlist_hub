"""Bungie OAuth (v2 Phase 3).

scope 는 앱 등록 시 고정(64=ReadDestinyInventoryAndVault) — 동적 scope 미지원.
Public / Confidential 클라이언트 모두 지원:
  * client_secret 이 있으면 Confidential(Authorization: Basic, 리프레시 토큰 발급).
  * 없으면 Public(토큰 요청 본문에 client_id, 리프레시 없음).
state/토큰은 로컬 DB 에 보관(단일 사용자 전제).
"""
from __future__ import annotations

import base64
import secrets
import sqlite3
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from .. import config, repo
from ..db import get_conn

router = APIRouter(tags=["auth (고도화)"])

TOKEN_URL = "https://www.bungie.net/Platform/App/OAuth/Token/"

# CSRF state — {state: 만료시각}. TTL + 최대 개수로 무한 증가/메모리 DoS 방지.
_states: dict = {}
_STATE_TTL = timedelta(minutes=10)
_STATE_MAX = 256


def _prune_states() -> None:
    now = datetime.now(timezone.utc)
    for s in [s for s, exp in _states.items() if exp < now]:
        _states.pop(s, None)
    # 그래도 과다하면 가장 오래된 것부터 제거(상한 강제)
    if len(_states) > _STATE_MAX:
        for s, _ in sorted(_states.items(), key=lambda kv: kv[1])[: len(_states) - _STATE_MAX]:
            _states.pop(s, None)


def _state_valid(state: str) -> bool:
    exp = _states.pop(state, None)
    return bool(exp) and exp >= datetime.now(timezone.utc)


def oauth_configured() -> bool:
    # 로그인/토큰 교환에는 client_id 만 있으면 된다(Public). secret 은 Confidential 일 때만.
    return bool(config.BUNGIE_OAUTH_CLIENT_ID)


def _is_confidential() -> bool:
    return bool(config.BUNGIE_OAUTH_CLIENT_SECRET)


def _token_post(client: httpx.Client, grant: dict) -> dict:
    """토큰 엔드포인트 호출 — Confidential 이면 Basic, Public 이면 본문 client_id."""
    headers = {"X-API-Key": config.BUNGIE_API_KEY, "Content-Type": "application/x-www-form-urlencoded"}
    data = dict(grant)
    if _is_confidential():
        raw = f"{config.BUNGIE_OAUTH_CLIENT_ID}:{config.BUNGIE_OAUTH_CLIENT_SECRET}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    else:
        data["client_id"] = config.BUNGIE_OAUTH_CLIENT_ID
    r = client.post(TOKEN_URL, headers=headers, data=data)
    r.raise_for_status()
    return r.json()


@router.get("/auth/bungie/login")
def bungie_login():
    if not oauth_configured():
        raise HTTPException(
            status_code=501,
            detail="Bungie OAuth 미설정. .env 에 BUNGIE_OAUTH_CLIENT_ID 를 설정하세요.",
        )
    _prune_states()
    state = secrets.token_urlsafe(16)
    _states[state] = datetime.now(timezone.utc) + _STATE_TTL
    params = {"response_type": "code", "client_id": config.BUNGIE_OAUTH_CLIENT_ID, "state": state}
    return RedirectResponse(config.BUNGIE_OAUTH_AUTHORIZE_URL + "?" + urllib.parse.urlencode(params))


@router.get("/auth/bungie/callback")
def bungie_callback(
    code: str = Query(...),
    state: str = Query(""),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if not oauth_configured():
        raise HTTPException(status_code=501, detail="Bungie OAuth 미설정.")
    if not _state_valid(state):
        raise HTTPException(status_code=400, detail="잘못된/만료된 state (CSRF).")

    with httpx.Client(timeout=30.0) as client:
        tok = _token_post(client, {"grant_type": "authorization_code", "code": code})
        access, refresh = tok["access_token"], tok.get("refresh_token")
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=tok.get("expires_in", 3600))).isoformat()

        mr = client.get(
            "https://www.bungie.net/Platform/User/GetMembershipsForCurrentUser/",
            headers={"X-API-Key": config.BUNGIE_API_KEY, "Authorization": f"Bearer {access}"},
        )
        mr.raise_for_status()
        memberships = mr.json()["Response"]["destinyMemberships"]
        primary = memberships[0] if memberships else None
        if not primary:
            raise HTTPException(status_code=400, detail="Destiny 멤버십을 찾을 수 없습니다.")

    repo.save_token(conn, primary["membershipId"], primary["membershipType"], access, refresh, expires_at)
    return RedirectResponse(f"{config.FRONTEND_URL}/?connected=1")


def access_token(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """저장된 토큰 반환(만료 시 refresh — Confidential 만). 없으면 None."""
    row = repo.get_token(conn)
    if not row:
        return None
    try:
        exp = datetime.fromisoformat(row["expires_at"])
    except Exception:
        exp = datetime.now(timezone.utc)
    if exp > datetime.now(timezone.utc) + timedelta(seconds=60):
        return row
    if not row["refresh_token"] or not _is_confidential():
        return row  # Public 클라이언트는 리프레시 불가 → 재로그인 필요
    try:
        with httpx.Client(timeout=30.0) as client:
            tok = _token_post(client, {"grant_type": "refresh_token", "refresh_token": row["refresh_token"]})
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=tok.get("expires_in", 3600))).isoformat()
        repo.save_token(conn, row["membership_id"], row["membership_type"],
                        tok["access_token"], tok.get("refresh_token", row["refresh_token"]), expires_at)
        return repo.get_token(conn, row["membership_id"])
    except Exception:
        return row
