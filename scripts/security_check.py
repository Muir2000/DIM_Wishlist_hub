"""보안 검증 스크립트 (반복 실행 가능).

정적(설정/소스) 점검 + 실행 중 앱 런타임 프로빙을 수행하고, 하나라도 실패하면 비0 종료한다.
표준 라이브러리만 사용(외부 의존 없음).

사용:
    python scripts/security_check.py                 # 기본 BASE=http://127.0.0.1:8080/api
    SECCHK_BASE=http://127.0.0.1:8000 python scripts/security_check.py   # 백엔드 직접

설계 기준(이 도구의 위협 모델): 단일 사용자 로컬 도구. 검증 항목은
SQLi/XSS/비밀노출/에러노출/입력 DoS/CORS/포트 노출/OAuth state 를 다룬다.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = os.getenv("SECCHK_BASE", "http://127.0.0.1:8080/api").rstrip("/")
TIMEOUT = 30

results: list = []  # (name, ok, detail)


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, bool(ok), detail))


def _req(method: str, path: str, body=None, headers=None):
    url = BASE + path
    data = None
    h = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # 연결 실패 등
        return -1, f"{type(e).__name__}: {e}"


TRACE_MARKERS = ("Traceback (most recent", "sqlite3.", 'File "/', "File \"C:\\", "OperationalError")


def no_trace(text: str) -> bool:
    return not any(m in text for m in TRACE_MARKERS)


# ---------------------------------------------------------------- 정적 점검
def static_checks():
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    pub = re.findall(r'-\s*"([^"]+:\d+)"', compose)
    bad = [p for p in pub if not p.startswith("127.0.0.1:")]
    check("정적: 도커 published 포트가 127.0.0.1 바인딩", not bad,
          f"비-로컬 바인딩: {bad}" if bad else "모든 published 포트 로컬 전용")

    gi = (REPO / ".gitignore").read_text(encoding="utf-8") if (REPO / ".gitignore").exists() else ""
    di = (REPO / ".dockerignore").read_text(encoding="utf-8") if (REPO / ".dockerignore").exists() else ""
    check("정적: .env 가 .gitignore 제외", ".env" in gi, "")
    check("정적: .env 가 .dockerignore 제외", ".env" in di, "")

    main_py = (REPO / "backend/app/main.py").read_text(encoding="utf-8")
    cors_wild = re.search(r'allow_origins\s*=\s*\[[^\]]*["\']\*["\']', main_py)
    check("정적: CORS allow_origins 와일드카드 아님", not cors_wild, "")

    nginx = (REPO / "docker/nginx.conf").read_text(encoding="utf-8")
    check("정적: nginx 업로드 한도(client_max_body_size) 설정", "client_max_body_size" in nginx, "")


# ---------------------------------------------------------------- 런타임 점검
def runtime_checks():
    st, body = _req("GET", "/health")
    check("런타임: /health 200", st == 200, f"status={st}")
    if st < 0:
        check("런타임: 서버 연결", False, f"{BASE} 에 연결 불가 — 스택을 먼저 기동하세요. ({body})")
        return

    # /status 비밀 미노출
    st, body = _req("GET", "/status")
    leak = bool(re.search(r"[0-9a-fA-F]{32}", body)) or "client_secret" in body or "access_token" in body
    check("런타임: /status 비밀키/토큰 미노출", st == 200 and not leak, body[:200])

    # SQLi 프로브 — 이름 검색
    for payload in ["' OR '1'='1", "x'); DROP TABLE weapons;--", "%27%20OR%201=1"]:
        st, body = _req("GET", f"/weapons?q={urllib.parse.quote(payload)}&limit=5")
        check(f"런타임: SQLi(q) 안전 [{payload[:18]}]", st in (200, 400, 422) and no_trace(body), f"status={st}")

    # SQLi 프로브 — 텍스트 쿼리 언어
    for payload in ["is:arc') OR 1=1--", "stat:range:>=50; DROP TABLE weapons", "frame:'||(SELECT)"]:
        st, body = _req("GET", f"/weapons?query={urllib.parse.quote(payload)}")
        check(f"런타임: SQLi(query) 안전 [{payload[:18]}]", st in (200, 400) and no_trace(body), f"status={st}")

    # 무기 무결성 — 주입 후에도 weapons 테이블 살아있는지
    st, body = _req("GET", "/weapons?limit=1")
    check("런타임: weapons 테이블 무결(주입 후 정상 조회)", st == 200 and body.strip().startswith("["), f"status={st}")

    # 카르테시안 폭발 차단 (/compile)
    cols = {str(i): list(range(1000, 1000 + 40)) for i in range(3)}  # 40^3 = 64000 > 상한
    st, body = _req("POST", "/compile", {"weapon_hash": 52683113, "columns": cols,
                                         "wildcard": False, "trash": False, "notes": "", "tags": [], "comment": ""})
    check("런타임: /compile 조합 폭발 차단(400)", st == 400 and no_trace(body), f"status={st}")

    # 대용량 import 차단 (>8MB → 422)
    big = "x" * (8_200_000)
    st, body = _req("POST", "/import-wishlist", {"text": big})
    check("런타임: /import-wishlist 대용량 차단(413/422)", st in (413, 422) and no_trace(body), f"status={st}")

    # 정상 import 는 동작
    st, body = _req("POST", "/import-wishlist", {"text": "title:t\n// W\ndimwishlist:item=52683113&perks=1,2\n"})
    check("런타임: /import-wishlist 정상 동작(200)", st == 200 and no_trace(body), f"status={st}")

    # 스탯 필터 잘못된 값 → 500 아님
    st, body = _req("GET", "/weapons?stat_min=handling:abc&limit=3")
    check("런타임: 잘못된 스탯필터 500 아님", st == 200 and no_trace(body), f"status={st}")

    # 잘못된 텍스트 쿼리 → 400 + 친절 메시지(트레이스백 아님)
    st, body = _req("GET", "/weapons?query=" + urllib.parse.quote("is:없는무기"))
    check("런타임: 잘못된 쿼리 400(트레이스백 없음)", st == 400 and no_trace(body), f"status={st} {body[:120]}")

    # 404 도 트레이스백 노출 안 함
    st, body = _req("GET", "/weapons/999999999")
    check("런타임: 404 트레이스백 미노출", st == 404 and no_trace(body), f"status={st}")

    # OAuth 콜백 잘못된 state → 500 아님(400/501)
    st, body = _req("GET", "/auth/bungie/callback?code=x&state=bogus")
    check("런타임: OAuth 잘못된 state 거부(400/501)", st in (400, 501) and no_trace(body), f"status={st}")


def main():
    static_checks()
    runtime_checks()
    print("\n=== 보안 검증 결과 ===")
    passed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {name}"
        if not ok and detail:
            line += f"  — {detail}"
        print(line)
        passed += ok
    total = len(results)
    print(f"\n{passed}/{total} 통과")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
