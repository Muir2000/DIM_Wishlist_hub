"""HMAC 서명 세션 쿠키 — Bungie OAuth 멤버십을 사용자 키로 식별.

쿠키 값: "<membership_id>.<hmac_hex>" (HMAC-SHA256, SESSION_SECRET 키).
상태 비저장(stateless): 별도 세션 테이블 없이 서명만으로 위·변조를 차단한다.
membership_id 는 공개값이라 기밀이 아니며, 서명은 무결성(위조 방지)만 보장한다.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import HTTPException, Request

from . import config

COOKIE_NAME = "dimhub_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30일


def _sig(membership_id: str) -> str:
    return hmac.new(config.SESSION_SECRET.encode("utf-8"),
                    membership_id.encode("utf-8"), hashlib.sha256).hexdigest()


def sign(membership_id: str) -> str:
    """쿠키에 저장할 서명된 값."""
    return f"{membership_id}.{_sig(membership_id)}"


def verify(cookie_value: Optional[str]) -> Optional[str]:
    """서명 검증 후 membership_id 반환(위조/없음이면 None)."""
    if not cookie_value or "." not in cookie_value:
        return None
    mid, _, sig = cookie_value.rpartition(".")  # membership_id 는 숫자라 '.' 없음
    if not mid or not sig:
        return None
    return mid if hmac.compare_digest(sig, _sig(mid)) else None


def current_membership(request: Request) -> Optional[str]:
    """현재 요청의 로그인 멤버십(없으면 None). FastAPI 의존성."""
    return verify(request.cookies.get(COOKIE_NAME))


def require_membership(request: Request) -> str:
    """로그인 필수 엔드포인트용 의존성. 미로그인은 401."""
    mid = current_membership(request)
    if not mid:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return mid
