# 아키텍처 & API

## 기술 스택

| 영역 | 스택 |
|---|---|
| 프론트엔드 | React 18 + Vite 5 + TypeScript (SPA). 상태: React Context. |
| 백엔드 | FastAPI + Uvicorn (Python 3.8+ 호환). |
| DB | SQLite (자체 경량 스키마, 매니페스트/시드에서 적재). |
| 적재 | Python + httpx (Bungie 매니페스트, voltron.txt). |
| 배포 | Docker Compose (backend + frontend(nginx)). 기본 포트 127.0.0.1 바인딩, `.env` `WEB_BIND=0.0.0.0` 시 LAN 공유. |
| 인증/멀티유저 | Bungie OAuth (Public/Confidential, scope 64) + **HMAC 서명 세션 쿠키**. 프로필·위시리스트·창고를 **사용자(membership)별 분리 저장**. |
| 다국어 | i18n(한국어 기본 + 영어 토글), UI 문자열 리소스(`i18n/ko.ts`·`en.ts`) + 데이터 `name_en` 폴백. |

## 디렉터리 구조

```
DIM_Wishlist_hub/
├─ backend/app/
│  ├─ compiler.py        # 위시리스트 컴파일러 + 파서(parse_wishlist) — DIM 포맷, 조합 상한
│  ├─ query.py           # DIM식 텍스트 쿼리 언어(토크나이저/파서/SQL 컴파일러/레지스트리)
│  ├─ seasons.py         # watermark→시즌(번호/이름) 매핑 (refdata 로드)
│  ├─ scoring.py         # 위시리스트 기반·퍽 롤 중심 점수화
│  ├─ main.py            # FastAPI 진입점 + CORS + 시작 시 DB 초기화
│  ├─ config.py / db.py / repo.py / models.py / serialize.py / labels.py
│  ├─ session.py         # HMAC 서명 세션 쿠키(멀티유저) 발급/검증
│  ├─ refdata/           # watermark-to-season.json, season-names.json
│  └─ routers/           # weapons, wishlist, meta, scoring, auth, inventory, state
├─ backend/seed/         # build_seed.py → seed_data.json
├─ backend/tests/        # test_compiler.py, test_query.py, test_scoring.py (총 74개)
├─ ingest/               # manifest_ingest.py, voltron_bootstrap.py
├─ frontend/src/
│  ├─ App.tsx, main.tsx, store.tsx, api.ts, auth.tsx, theme.css
│  ├─ i18n/              # LanguageProvider/useLanguage(기본 ko) + en.ts·ko.ts + 라벨 헬퍼 (한/영)
│  ├─ hooks/             # useToggleSet (다중선택 공용)
│  ├─ utils/             # clipboard (useCopyState 공용)
│  └─ components/        # WeaponSearch, PerkGrid, PerkIcon, StatsPanel, Builder, OwnedRoll,
│                        #   WishlistPanel, ListRail, MetaDashboard, ScoringProfileEditor, InventoryCleanup
├─ scripts/dev-local.mjs        # WebDAV 우회 dev 실행
├─ scripts/security_check.py    # 보안 검증(정적+런타임 21항목)
├─ docker/                      # backend.Dockerfile, frontend.Dockerfile, nginx.conf
├─ docker-compose.yml
├─ data/                        # SQLite 산출물 (git 미추적)
└─ docs/MD/                     # 본 문서
```

## 데이터 흐름

```
Bungie API ─(manifest_ingest)─▶ SQLite(weapons/perks/weapon_perks/weapon_stats/perk_stats/stat_defs)
voltron.txt ─(voltron_bootstrap)─▶ SQLite(roll_stats)
                                        │
React SPA ─(/api, nginx 또는 Vite 프록시)─ FastAPI(검색/패싯/컴파일/내보내기/가져오기/점수/메타/OAuth) ◀┘
   └─ 컴파일 .txt 다운로드 → DIM 업로드 / 외부 .txt 가져오기 → 롤 로드
```
실 DB(`data/app.sqlite`) 없으면 시작 시 `seed_data.json` → `data/seed_cache.sqlite` 생성(상태=seed).

## DB 스키마 (SQLite)

| 테이블 | 핵심 컬럼 |
|---|---|
| `manifest_meta` | version, ingested_at, locale, source(seed/manifest) |
| `weapons` | item_hash(PK), name_ko/en, icon, watermark, tier, weapon_subtype, ammo_type, slot, default_damage_type, **frame, frame_en, frame_hash, is_holofoil, is_adept, is_featured, variant_group**, redacted |
| `perks` | plug_hash(PK), name_ko/en, **description_ko, description_en**, icon, plug_category, is_enhanced, base_plug_hash |
| `weapon_perks` | weapon_hash, column_index, column_kind, plug_hash, currently_can_roll, is_curated |
| `roll_stats` | weapon_hash, column_index, plug_hash, count, source(voltron) |
| `stat_defs` | stat_hash(PK), key, name_ko, name_en |
| `weapon_stats` | weapon_hash, stat_key, value (표시 스탯, long-format) |
| `perk_stats` | plug_hash, stat_key, value, is_conditional (퍽 델타) |
| `scoring_profiles` | id(PK), name, json(blob), **owner**(membership_id, 사용자별), updated_at |
| `user_state` | **owner(PK)**, json({rolls,title,description,activeProfileId}), updated_at — 사용자별 빌더 상태 |
| `oauth_tokens` | membership_id(PK), membership_type, access/refresh_token, expires_at, **display_name** |
| `inventory_items` | item_instance_id(PK), membership_id, item_hash, plug_hashes(JSON), stats(JSON), power, synced_at, **reusable_plugs**(JSON; 310 열별 선택 가능 퍽, 제작=다중) |

> `apply_schema` 가 기존 DB 에 누락 컬럼을 `ALTER TABLE` 로 마이그레이션(description_*, frame_en, is_holofoil,
> scoring_profiles.owner, oauth_tokens.display_name, inventory_items.reusable_plugs 등) — 레거시 DB 호환.

## API 엔드포인트

| 메서드 · 경로 | 설명 |
|---|---|
| `GET /health` · `GET /status` | 헬스 · 데이터 소스/버전/무기 수/키 설정 여부(bool) |
| `GET /weapons` | 무기 검색 — `q`, 다중값 CSV(`subtypes/tiers/damages/slots/ammo/frames/origins/seasons`), `perks`/`perk_exclude`/`perkname`, `stat_min/max`, **`query`**(텍스트 쿼리), `limit`. 시즌 단위 접기 |
| `GET /weapons/count` | 현재 필터/검색 매칭 무기(시즌그룹) **총 건수** (LIMIT 무관) |
| `GET /weapons/{hash}` | 무기 상세 + 열별 퍽 풀(설명·스탯델타·인기도·배지·변형/시즌) |
| `GET /filters` | **컨텍스트 인지 패싯** — 현재 검색/필터 기준 카테고리별 가용 값+갯수(자기 필터 제외) |
| `GET /search/help` | 텍스트 쿼리 지원 토큰·예시(치트시트) |
| `GET /perks?q=` · `GET /stat-defs` | 퍽 자동완성 · 스탯 정의 |
| `POST /compile` · `POST /export` | 단일 롤 미리보기 · 완성 `.txt`(조합 폭발 시 400) |
| `POST /import-wishlist` | 외부 DIM `.txt` → 롤 목록(제목/설명/집계). text 최대 8MB |
| `GET /meta/top-weapons` · `GET /meta/weapon/{hash}/perk-popularity` | 인기 무기 · 열별 인기도 |
| `GET/POST/DELETE /scoring-profiles[/{id}]` | 점수 프로필 CRUD(JSON=공유 단위). **로그인 시 사용자(owner)별** 목록 |
| `POST /score` | 점수·분류·breakdown·coverage·max_possible |
| `POST /score/perk-weights` | 퍽별 가중치 맵(+scale·max_possible·coverage·column_weights·kinds) — 빌더 퍽 배지 |
| `POST /score/tags` | **태그별(PvE/PvP/GM/레이드) 점수 + 추천 퍽** + overall — 빌더 태그 점수/추천 |
| `POST /scoring/derive-weights` | 위시리스트(롤/텍스트)→컨텍스트 가중치 도출 |
| `GET /auth/bungie/login` · `/callback` · `GET /auth/me` · `POST /auth/logout` | Bungie OAuth(state CSRF) + 세션 쿠키 발급/조회/해제 |
| `GET /me/state` · `PUT /me/state` | 사용자별 빌더 상태(롤/제목/설명/활성 프로필) 조회·저장 |
| `GET /me/status` · `POST /me/sync` · `/me/demo-inventory` | 창고 연동(동기화/데모) |
| `POST /me/cleanup` · `/me/weapon-rolls` · `/me/export-trashlist` · `GET /me/debug-rolls` | 창고 채점·무기별 롤·트래시리스트·진단 |

Swagger UI: `http://127.0.0.1:8000/docs` (백엔드 포트는 127.0.0.1 바인딩 — 로컬 전용).
멀티유저: `/scoring-profiles`·`/me/*` 는 세션 쿠키의 membership 으로 데이터를 분리한다(미로그인 시 레거시/공개 범위).

## 컴파일러 핵심 (정확성)

DIM `wishlist-file.ts` 정규식 호환:
```
^dimwishlist:item=(-?\d+)(?:&perks=)?([\d|,]*)(?:#notes:)?([^|]*)
```
- 쉼표=AND · 다중 퍽→다중줄(카르테시안, 상한 2000) · 트래시=음수 해시 · 와일드카드=-69420 ·
  강화 퍽 미출력 · 노트 `|` 제거 · LF/BOM 없음 · 변형 그룹 전개.
- `parse_wishlist`: 전체 파일 역파싱(헤더/주석/블록노트/멀티라인 역병합) — 가져오기용.
- 테스트: `cd backend && python -m unittest discover -s tests` (74개: compiler 30 + query 21 + scoring 23).

## 배포 (Docker)
- `docker compose build && docker compose up -d` → 앱 `http://localhost:8080`(nginx, `/api`→backend).
- `docker compose run --rm ingest python -m ingest.manifest_ingest --force` 후 `docker compose restart backend`.
- 포트는 127.0.0.1 바인딩(로컬 전용), nginx `client_max_body_size 16m`. 상세는 [04-개발환경-실행.md](04-개발환경-실행.md).
