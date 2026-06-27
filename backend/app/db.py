"""SQLite 스키마 · 연결 · 시드 적재.

데이터 소스 결정(앱 시작 시 1회):
  * 실제 적재된 DB(data/app.sqlite)에 무기가 있으면 그것을 사용(source="manifest").
  * 없으면 seed_data.json 으로 캐시 DB(data/seed_cache.sqlite)를 새로 만들어 사용(source="seed").

요청 처리는 활성 DB 경로로 매 요청 새 연결을 연다(스레드 안전).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS manifest_meta (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    version     TEXT,
    ingested_at TEXT,
    locale      TEXT,
    source      TEXT
);
CREATE TABLE IF NOT EXISTS weapons (
    item_hash           INTEGER PRIMARY KEY,
    name_ko             TEXT,
    name_en             TEXT,
    icon                TEXT,
    watermark           TEXT,
    tier                INTEGER,
    weapon_subtype      INTEGER,
    ammo_type           INTEGER,
    slot                TEXT,
    default_damage_type TEXT,
    frame               TEXT,
    frame_en            TEXT,
    frame_hash          INTEGER,
    is_holofoil         INTEGER DEFAULT 0,   -- 외형만 다른 홀로포일 변형 (성능 동일)
    is_adept            INTEGER DEFAULT 0,   -- 에이뎁트 변형
    is_featured         INTEGER DEFAULT 0,   -- featured/복각 표시
    variant_group       TEXT,                -- 변형/복각 그룹 키 (name_en|subtype)
    redacted            INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS perks (
    plug_hash      INTEGER PRIMARY KEY,
    name_ko        TEXT,
    name_en        TEXT,
    description_ko TEXT,
    description_en TEXT,
    icon           TEXT,
    plug_category  TEXT,
    is_enhanced    INTEGER DEFAULT 0,
    base_plug_hash INTEGER
);
CREATE TABLE IF NOT EXISTS weapon_perks (
    weapon_hash        INTEGER,
    column_index       INTEGER,
    column_kind        TEXT,
    plug_hash          INTEGER,
    currently_can_roll INTEGER DEFAULT 1,
    is_curated         INTEGER DEFAULT 0,
    PRIMARY KEY (weapon_hash, column_index, plug_hash)
);
CREATE TABLE IF NOT EXISTS roll_stats (
    weapon_hash  INTEGER,
    column_index INTEGER,
    plug_hash    INTEGER,
    count        INTEGER DEFAULT 0,
    source       TEXT,
    PRIMARY KEY (weapon_hash, column_index, plug_hash, source)
);

-- v2: 스탯 메타 / 무기 표시 스탯 / 퍽 스탯 델타
CREATE TABLE IF NOT EXISTS stat_defs (
    stat_hash INTEGER PRIMARY KEY,
    key       TEXT,        -- 정규화 키: handling/range/stability/...
    name_ko   TEXT,
    name_en   TEXT
);
CREATE TABLE IF NOT EXISTS weapon_stats (
    weapon_hash INTEGER,
    stat_key    TEXT,
    value       REAL,
    PRIMARY KEY (weapon_hash, stat_key)
);
CREATE TABLE IF NOT EXISTS perk_stats (
    plug_hash      INTEGER,
    stat_key       TEXT,
    value          REAL,
    is_conditional INTEGER DEFAULT 0,
    PRIMARY KEY (plug_hash, stat_key)
);

-- v2: 점수화 프로필 (프로필 전체를 JSON blob 으로 보관 = 파일 공유 포맷과 동일)
CREATE TABLE IF NOT EXISTS scoring_profiles (
    id         TEXT PRIMARY KEY,
    name       TEXT,
    json       TEXT,
    owner      TEXT,                -- 소유 사용자(Bungie membership_id). NULL=레거시(미표시)
    updated_at TEXT
);

-- 사용자별 빌더 상태(위시리스트 롤 + 활성 프로필). owner=membership_id.
CREATE TABLE IF NOT EXISTS user_state (
    owner      TEXT PRIMARY KEY,
    json       TEXT,                -- {rolls, title, description, activeProfileId}
    updated_at TEXT
);

-- v2: Bungie OAuth 토큰 / 인벤토리 스냅샷
CREATE TABLE IF NOT EXISTS oauth_tokens (
    membership_id   TEXT PRIMARY KEY,
    membership_type INTEGER,
    access_token    TEXT,
    refresh_token   TEXT,
    expires_at      TEXT,
    display_name    TEXT
);
CREATE TABLE IF NOT EXISTS inventory_items (
    item_instance_id TEXT PRIMARY KEY,
    membership_id    TEXT,
    item_hash        INTEGER,
    plug_hashes      TEXT,   -- JSON 배열 (305 장착 퍽)
    stats            TEXT,   -- JSON {stat_key: value} (304 사전계산)
    power            INTEGER,
    synced_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_wp_weapon   ON weapon_perks(weapon_hash);
CREATE INDEX IF NOT EXISTS idx_weapons_ko  ON weapons(name_ko);
CREATE INDEX IF NOT EXISTS idx_weapons_en  ON weapons(name_en);
CREATE INDEX IF NOT EXISTS idx_rs_weapon   ON roll_stats(weapon_hash);
CREATE INDEX IF NOT EXISTS idx_ws_weapon   ON weapon_stats(weapon_hash);
CREATE INDEX IF NOT EXISTS idx_ps_plug     ON perk_stats(plug_hash);
CREATE INDEX IF NOT EXISTS idx_inv_member  ON inventory_items(membership_id);
-- idx_profiles_owner 는 apply_schema 에서 owner 컬럼 보강 후 생성(레거시 DB 호환).
"""

# 시작 시 결정되는 활성 DB 정보
_active_path: Optional[Path] = None
_active_source: str = "seed"
_active_version: str = ""


def connect(path: Path) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI 의 sync 의존성은 스레드풀에서 동작하며 생성/teardown 이
    # 다른 스레드일 수 있다. 연결은 요청당 1개(공유 없음)이므로 안전하다.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # 기존 DB 마이그레이션: perks 에 description 컬럼 추가
    for col in ("description_ko", "description_en"):
        try:
            conn.execute(f"ALTER TABLE perks ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # 이미 존재
    # weapons 에 변형(복각/홀로포일) 컬럼 추가
    for col, decl in (
        ("is_holofoil", "INTEGER DEFAULT 0"),
        ("is_adept", "INTEGER DEFAULT 0"),
        ("is_featured", "INTEGER DEFAULT 0"),
        ("variant_group", "TEXT"),
        ("frame_en", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE weapons ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass
    # 멀티유저: scoring_profiles 소유자, oauth_tokens 표시명 추가(구 DB 보강)
    for table, col, decl in (
        ("scoring_profiles", "owner", "TEXT"),
        ("oauth_tokens", "display_name", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass
    # owner 컬럼이 보강된 뒤에야 인덱스를 만들 수 있다(레거시 DB 는 위 ALTER 전까지 owner 부재).
    conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_owner ON scoring_profiles(owner)")
    conn.commit()


def _has_weapons(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        conn = connect(path)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='weapons'"
            ).fetchone()
            if not row:
                return False
            n = conn.execute("SELECT COUNT(*) AS c FROM weapons").fetchone()["c"]
            return n > 0
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def load_seed(conn: sqlite3.Connection, seed_path: Path) -> Tuple[str, int]:
    """seed_data.json 을 빈 DB 에 적재. (version, weapon_count) 반환."""
    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    version = data.get("manifest", {}).get("version", "SEED")
    locale = data.get("manifest", {}).get("locale", "ko")

    cur = conn.cursor()
    for w in data["weapons"]:
        cur.execute(
            """INSERT OR REPLACE INTO weapons
               (item_hash,name_ko,name_en,icon,watermark,tier,weapon_subtype,
                ammo_type,slot,default_damage_type,frame,frame_hash,redacted)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)""",
            (w["item_hash"], w.get("name_ko"), w.get("name_en"), w.get("icon"),
             w.get("watermark"), w.get("tier"), w.get("weapon_subtype"),
             w.get("ammo_type"), w.get("slot"), w.get("default_damage_type"),
             w.get("frame"), w.get("frame_hash")),
        )
        for stat_key, val in (w.get("stats") or {}).items():
            cur.execute(
                "INSERT OR REPLACE INTO weapon_stats (weapon_hash,stat_key,value) VALUES (?,?,?)",
                (w["item_hash"], stat_key, val),
            )
        for col in w["columns"]:
            for p in col["perks"]:
                cur.execute(
                    """INSERT OR REPLACE INTO perks
                       (plug_hash,name_ko,name_en,description_ko,description_en,icon,plug_category,is_enhanced,base_plug_hash)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (p["plug_hash"], p.get("name_ko"), p.get("name_en"),
                     p.get("description_ko"), p.get("description_en"),
                     p.get("icon"), p.get("plug_category"), p.get("is_enhanced", 0), p.get("base_plug_hash")),
                )
                for stat_key, val in (p.get("stats") or {}).items():
                    cur.execute(
                        "INSERT OR REPLACE INTO perk_stats (plug_hash,stat_key,value,is_conditional) VALUES (?,?,?,0)",
                        (p["plug_hash"], stat_key, val),
                    )
                cur.execute(
                    """INSERT OR REPLACE INTO weapon_perks
                       (weapon_hash,column_index,column_kind,plug_hash,currently_can_roll,is_curated)
                       VALUES (?,?,?,?,?,?)""",
                    (w["item_hash"], col["index"], col["kind"], p["plug_hash"],
                     p.get("currently_can_roll", 1), p.get("is_curated", 0)),
                )

    for sd in data.get("stat_defs", []):
        cur.execute(
            "INSERT OR REPLACE INTO stat_defs (stat_hash,key,name_ko,name_en) VALUES (?,?,?,?)",
            (sd["stat_hash"], sd["key"], sd.get("name_ko"), sd.get("name_en")),
        )

    for rs in data.get("roll_stats", []):
        cur.execute(
            """INSERT OR REPLACE INTO roll_stats
               (weapon_hash,column_index,plug_hash,count,source) VALUES (?,?,?,?,?)""",
            (rs["weapon_hash"], rs["column_index"], rs["plug_hash"], rs["count"],
             rs.get("source", "voltron")),
        )

    cur.execute(
        "INSERT OR REPLACE INTO manifest_meta (id,version,ingested_at,locale,source) VALUES (1,?,?,?,?)",
        (version, datetime.now(timezone.utc).isoformat(), locale, "seed"),
    )
    conn.commit()
    return version, len(data["weapons"])


def init_active_db() -> Tuple[Path, str, str]:
    """활성 DB 를 결정/준비한다. (path, source, version) 반환."""
    global _active_path, _active_source, _active_version

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    if _has_weapons(config.DB_PATH):
        conn = connect(config.DB_PATH)
        try:
            apply_schema(conn)  # 멀티유저 등 신규 테이블/컬럼 보강(idempotent)
            row = conn.execute(
                "SELECT version, source FROM manifest_meta WHERE id=1"
            ).fetchone()
        finally:
            conn.close()
        _active_path = config.DB_PATH
        _active_source = (row["source"] if row and row["source"] else "manifest")
        _active_version = (row["version"] if row else "") or ""
        return _active_path, _active_source, _active_version

    # 시드 모드: 시드 버전이 동일하면 기존 캐시 재사용(프로필/토큰/인벤토리 등 사용자 데이터 보존),
    # 버전이 바뀌었거나 캐시가 없으면 새로 빌드.
    with open(config.SEED_PATH, "r", encoding="utf-8") as f:
        seed_version = json.load(f).get("manifest", {}).get("version", "SEED")

    reuse = False
    if config.SEED_CACHE_PATH.exists() and _has_weapons(config.SEED_CACHE_PATH):
        c = connect(config.SEED_CACHE_PATH)
        try:
            r = c.execute("SELECT version FROM manifest_meta WHERE id=1").fetchone()
            reuse = bool(r and r["version"] == seed_version)
            if reuse:
                apply_schema(c)  # 새 테이블 보강 (idempotent)
        finally:
            c.close()

    if not reuse:
        if config.SEED_CACHE_PATH.exists():
            config.SEED_CACHE_PATH.unlink()
        conn = connect(config.SEED_CACHE_PATH)
        try:
            apply_schema(conn)
            seed_version, _ = load_seed(conn, config.SEED_PATH)
        finally:
            conn.close()

    _active_path = config.SEED_CACHE_PATH
    _active_source = "seed"
    _active_version = seed_version
    return _active_path, _active_source, _active_version


def active_info() -> Tuple[Path, str, str]:
    if _active_path is None:
        return init_active_db()
    return _active_path, _active_source, _active_version


def get_conn() -> sqlite3.Connection:
    """FastAPI 의존성: 요청마다 활성 DB 새 연결."""
    path, _, _ = active_info()
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()
