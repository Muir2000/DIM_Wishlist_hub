# 데이터 적재 파이프라인

`backend/seed/seed_data.json` 의 샘플 데이터 대신 **실제 Bungie 매니페스트**로 앱을 구동하려면
아래 두 스크립트를 차례로 실행한다. 산출물은 `data/app.sqlite` 이며, 백엔드가 시작 시 이를
자동으로 감지해 시드 대신 사용한다.

## 사전 준비
1. https://www.bungie.net/en/Application 에서 애플리케이션을 만들고 **API Key** 발급.
2. 프로젝트 루트 `.env` 에 키 설정 (`.env.example` 복사):
   ```
   BUNGIE_API_KEY=발급받은_키
   MANIFEST_LOCALE=ko
   ```
3. 백엔드 의존성(httpx 포함)이 설치된 상태여야 한다 (`backend/requirements.txt`).

## 1) 매니페스트 적재
```bash
# repo 루트에서, 백엔드 venv 의 python 으로 실행
python -m ingest.manifest_ingest            # version 이 바뀐 경우에만 적재
python -m ingest.manifest_ingest --force    # 강제 재적재
python -m ingest.manifest_ingest --limit 200  # 개발용: 무기 200개만
```
무기/퍽/소켓을 정제해 `weapons`, `perks`, `weapon_perks` 테이블에 기록한다.
`currentlyCanRoll` 은 매니페스트 버전마다 바뀌므로, 새 시즌/패치 후 재실행 권장.

## 2) 메타/인기도 부트스트랩 (선택)
매니페스트 적재 후 실행. 커뮤니티 집계 위시리스트(voltron)를 파싱해 무기별·열별 퍽
추천 빈도를 `roll_stats` 에 기록 → 메타 대시보드와 인기도 막대를 채운다.
```bash
python -m ingest.voltron_bootstrap                 # URL 에서 다운로드
python -m ingest.voltron_bootstrap --file ./voltron.txt   # 로컬 파일
```

## 실행 예 (Windows PowerShell)
```powershell
cd Y:\Project\destiny\DIM_Wishlist_hub
$env:PYTHONUTF8=1
backend\.venv\Scripts\python.exe -m ingest.manifest_ingest
backend\.venv\Scripts\python.exe -m ingest.voltron_bootstrap
```

## 참고
- 적재는 JSON 컴포넌트 방식(`jsonWorldComponentContentPaths`)을 사용한다 — SQLite `.content`
  의 signed-int 해시 변환을 피하고 필요한 테이블만 내려받기 위함.
- 퍽 풀 해석: `socketEntries[i].randomizedPlugSetHash` → `DestinyPlugSetDefinition.reusablePlugItems`
  → `plugItemHash` + `currentlyCanRoll`.
- 강화(Enhanced) 퍽의 기본 퍽 매핑은 현재 미적용(`base_plug_hash=NULL`). 랜덤 롤 풀은
  기본 퍽으로 구성되므로 v1 컴파일에는 문제없으나, 정밀 매핑은 DIM `d2-additional-info` 참조.
