"""DIM Wishlist Maker Hub — FastAPI 진입점."""
from __future__ import annotations

import sqlite3

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, repo
from .db import get_conn
from .models import StatusOut
from .routers import auth, inventory, meta, scoring, weapons, wishlist

app = FastAPI(
    title="DIM Wishlist Maker Hub API",
    description="데스티니 가디언즈 위시리스트를 시각적으로 만들고 DIM 포맷으로 내보내는 백엔드.",
    version="0.1.0",
)

# 프론트 개발 서버(Vite)만 허용. 도커 배포는 nginx 동일 출처(/api)라 CORS 미사용.
# 추가 출처가 필요하면 FRONTEND_URL 을 허용 목록에 더한다.
_cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
if config.FRONTEND_URL and config.FRONTEND_URL not in _cors_origins:
    _cors_origins.append(config.FRONTEND_URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,                       # 명시적 허용 목록(와일드카드 금지 — credentials 동반)
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(weapons.router)
app.include_router(wishlist.router)
app.include_router(meta.router)
app.include_router(scoring.router)
app.include_router(auth.router)
app.include_router(inventory.router)


@app.on_event("startup")
def _startup():
    path, source, version = db.init_active_db()
    print(f"[DB] active={path} source={source} version={version}")


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/status", response_model=StatusOut, tags=["system"])
def status(conn: sqlite3.Connection = Depends(get_conn)):
    _, source, version = db.active_info()
    note = None
    if source == "seed":
        note = (
            "샘플 데이터로 구동 중. 실제 무기/퍼크를 쓰려면 `python -m ingest.manifest_ingest` 로 "
            "Bungie 매니페스트를 적재하세요."
        )
    return StatusOut(
        data_source=source,
        manifest_version=version,
        weapons=repo.weapons_count(conn),
        bungie_key_configured=bool(config.BUNGIE_API_KEY),
        note=note,
    )
