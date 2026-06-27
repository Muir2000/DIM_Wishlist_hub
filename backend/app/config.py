"""환경 설정 (.env 로드 포함)."""
import os
import secrets
from pathlib import Path

try:  # python-dotenv 는 선택 의존성
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"
SEED_PATH = BACKEND_DIR / "seed" / "seed_data.json"

BUNGIE_ROOT = "https://www.bungie.net"

BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY", "").strip()
MANIFEST_LOCALE = os.getenv("MANIFEST_LOCALE", "ko").strip() or "ko"
MANIFEST_LOCALE_FALLBACK = os.getenv("MANIFEST_LOCALE_FALLBACK", "en").strip() or "en"
VOLTRON_URL = os.getenv(
    "VOLTRON_URL",
    "https://raw.githubusercontent.com/48klocs/dim-wish-list-sources/master/voltron.txt",
).strip()

# OAuth (창고 가져오기/정리)
BUNGIE_OAUTH_CLIENT_ID = os.getenv("BUNGIE_OAUTH_CLIENT_ID", "").strip()
BUNGIE_OAUTH_CLIENT_SECRET = os.getenv("BUNGIE_OAUTH_CLIENT_SECRET", "").strip()
BUNGIE_OAUTH_AUTHORIZE_URL = os.getenv(
    "BUNGIE_OAUTH_AUTHORIZE_URL", "https://www.bungie.net/en/OAuth/Authorize"
).strip()
BUNGIE_OAUTH_REDIRECT_URI = os.getenv(
    "BUNGIE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/auth/bungie/callback"
).strip()
# OAuth 콜백 성공 후 리다이렉트할 프론트엔드 주소
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").strip()


def _resolve_db_path() -> Path:
    raw = os.getenv("DB_PATH", "").strip()
    if not raw:
        return DATA_DIR / "app.sqlite"
    p = Path(raw)
    return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


DB_PATH = _resolve_db_path()
SEED_CACHE_PATH = DATA_DIR / "seed_cache.sqlite"


def _load_session_secret() -> str:
    """세션 쿠키 서명 키. env(SESSION_SECRET) 우선, 없으면 DATA_DIR 에 1회 생성·영속
    (재시작 후에도 쿠키 유지). 파일 기록 불가 시 임시 키(재시작마다 재로그인 필요)."""
    val = os.getenv("SESSION_SECRET", "").strip()
    if val:
        return val
    path = DATA_DIR / ".session_secret"
    try:
        if path.exists():
            saved = path.read_text(encoding="utf-8").strip()
            if saved:
                return saved
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_hex(32)
        path.write_text(generated, encoding="utf-8")
        return generated
    except OSError:
        return secrets.token_hex(32)


SESSION_SECRET = _load_session_secret()
# 쿠키 Secure 속성: https 배포 시 SESSION_COOKIE_SECURE=1 로 켠다(기본 off — NAS http).
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "").strip() in ("1", "true", "True")
