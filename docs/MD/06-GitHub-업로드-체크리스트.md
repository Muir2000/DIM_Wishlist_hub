# GitHub 업로드 체크리스트

GitHub에 올리기 전 확인할 항목을 정리한다. 루트 README는 프로젝트 소개와 실행 진입점, 이 문서는 업로드/첫 push 전 점검용이다.

## 1. 커밋에 포함할 것

- `README.md`
- `.env.example`
- `.gitignore`, `.gitattributes`, `.dockerignore`
- `backend/app/`, `backend/seed/`, `backend/tests/`, `backend/requirements.txt`
- `frontend/src/`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/tsconfig*.json`, `frontend/vite.config.ts`, `frontend/index.html`
- `ingest/`, `docker/`, `scripts/`, `docs/MD/`
- `.github/workflows/ci.yml`

## 2. 커밋에 포함하지 말 것

- `.env` 실제 자격증명
- `data/*.sqlite`, `data/*.db`, SQLite runtime 데이터
- `frontend/node_modules/`
- `backend/.venv/`
- `__pycache__/`, `.pytest_cache/`, `*.pyc`
- `.claude/`, `.agents/`, `.codex/`, `.openai/` 같은 로컬 도구 상태
- `wish_list_test.txt` 같은 외부 위시리스트 덤프/수동 테스트 파일
- 로그, coverage, 임시 파일

## 3. 업로드 전 로컬 검증

백엔드 단위 테스트:

```bash
cd backend
python -m unittest discover -s tests
```

프론트엔드 빌드:

```bash
cd frontend
npm ci
npm run build
```

이 머신의 WebDAV 경로에서는 Vite가 `dist/assets` 생성 중 `EPERM` 또는 경로 정규화 문제로 실패할 수 있다. 이 경우 일반 로컬 디스크 복사본이나 GitHub Actions CI에서 최종 빌드를 확인한다.

보안 검증은 앱 또는 백엔드가 실행 중일 때 수행한다.

```bash
python scripts/security_check.py
```

백엔드 직접 검증:

```powershell
$env:SECCHK_BASE="http://127.0.0.1:8000"; python scripts/security_check.py
```

## 4. 첫 GitHub push 절차 예시

현재 폴더가 아직 Git 저장소가 아니라면:

```bash
git init
git status --ignored
git add README.md .env.example .gitignore .gitattributes .dockerignore docker-compose.yml backend frontend ingest docker scripts docs .github
git status
git commit -m "Initial commit"
git branch -M main
git remote add origin <github-repo-url>
git push -u origin main
```

`git status --ignored`에서 `.env`, `data/`, `node_modules/`, `.venv/`가 ignored로 보이는지 확인한다.

## 5. 큰 파일 처리

`wish_list_test.txt`처럼 재현 가능한 외부 테스트 덤프는 기본적으로 커밋하지 않는다. 꼭 보존해야 한다면 GitHub Release asset, 별도 fixture 저장소, 또는 Git LFS 사용을 검토한다.

## 6. GitHub Actions

`.github/workflows/ci.yml`은 push/PR마다 다음을 수행한다.

- Python 3.11에서 백엔드 의존성 설치 후 `python -m unittest discover -s tests`
- Node 20에서 `npm ci` 후 `npm run build`

보안 검증은 실행 중인 서버가 필요하므로 Actions에는 기본 포함하지 않았다.