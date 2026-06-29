# 외부 공개 & HTTPS 배포 (Nginx Proxy Manager)

NAS(UGREEN DXP4800 Plus, UGOS)에서 구동 중인 앱을 **외부 도메인 + HTTPS**로 공개한 작업 기록.
도메인 `muir20.ddns.net` 에 Let's Encrypt 인증서를 적용하고, Bungie OAuth 로그인까지
외부 HTTPS 환경에서 동작하도록 구성한다.

> ⚠️ 보안 주의: 이 앱은 이제 **Bungie 로그인 멀티유저**(사용자별 프로필·창고 분리)를 지원하므로 외부 공개의
> 기본 전제는 충족된다(→ [05-보안검증.md](05-보안검증.md)). 다만 **쿠키 Secure 플래그·멀티유저 자동 검증
> 항목은 보강 필요**, OAuth redirect/`FRONTEND_URL` 은 공개 도메인과 일치시킬 것. 신뢰 가능한 사용자 범위로 공개 권장.

---

## 1. 전체 구성 (요청 흐름)

```
인터넷
  │  https://muir20.ddns.net  (443)
  ▼
[공유기]  포트포워딩 80→41537, 443→41391
  ▼
[NAS 192.168.0.101]
  ├─ Nginx Proxy Manager (jc21_nginx-proxy-manager-1)
  │     호스트포트 41537→80, 41391→443, 33925→81(관리)
  │     · TLS 종료(Let's Encrypt) · Force SSL · HTTP/2
  │     · 프록시: muir20.ddns.net → http://192.168.0.101:8080
  ▼
  ├─ frontend (dim_wishlist_hub-frontend-1)  8080→80
  │     nginx: /  → 정적 SPA
  │            /api/ → http://backend:8000/  (compose 네트워크 DNS)
  ▼
  └─ backend (dim_wishlist_hub-backend-1)  uvicorn :8000
        DB: /app/data/app.sqlite  (바인드 ./data)
```

핵심: **TLS는 NPM에서 종료**되고, NPM→프론트→백엔드 내부 구간은 평문 HTTP다.
따라서 NPM 프록시의 업스트림 Scheme은 반드시 `http`여야 한다(§5 함정 2).

### 환경 값 (현 배포 기준)

| 항목 | 값 |
|---|---|
| 도메인 | `muir20.ddns.net` (No-IP DDNS) |
| 공인 IP | 112.153.132.252 (통신사 LG U+) |
| NAS LAN IP | 192.168.0.101 |
| NPM 관리화면 | `http://192.168.0.101:33925` |
| NPM HTTP/HTTPS 호스트포트 | 41537 / 41391 |
| 앱 공개 포트 | 8080 (frontend) |

---

## 2. 사전 점검 (DNS / 포트)

```powershell
# DDNS 가 현재 공인 IP 를 가리키는지
nslookup muir20.ddns.net
(Invoke-RestMethod "https://api.ipify.org?format=json").ip   # 둘이 같아야 함

# NPM HTTP/HTTPS 포트가 LAN 에서 열려 있는지
Test-NetConnection 192.168.0.101 -Port 41537   # HTTP
Test-NetConnection 192.168.0.101 -Port 41391   # HTTPS
```

> LG U+ 등 일부 가정 회선은 **80포트를 차단**한다. Let's Encrypt HTTP-01 인증과
> HTTP→HTTPS 리다이렉트에 80이 필요하므로, 포워딩 후 외부에서 반드시 개방 확인할 것
> (`portchecker.co` 또는 휴대폰 LTE 로 `http://muir20.ddns.net` 접속).

---

## 3. 공유기 포트포워딩

| 외부 포트 | 내부 IP : 포트 | 용도 |
|---|---|---|
| 80 (TCP) | 192.168.0.101 : **41537** | Let's Encrypt 인증 + HTTP 리다이렉트 |
| 443 (TCP) | 192.168.0.101 : **41391** | HTTPS 서비스 |

NPM 컨테이너가 표준 80/443이 아닌 41537/41391에 매핑돼 있으므로, **외부 표준 포트를
NPM의 실제 호스트 포트로** 포워딩한다(NAS 시스템 UI와의 80/443 충돌 회피).

---

## 4. NPM 프록시 호스트 + SSL

관리화면(`http://192.168.0.101:33925`) → **Hosts → Proxy Hosts → Add Proxy Host**

**Details 탭**
- Domain Names: `muir20.ddns.net`
- Scheme: **`http`**  ← 내부 구간은 평문(중요)
- Forward Hostname/IP: `192.168.0.101`
- Forward Port: `8080`
- ✅ Block Common Exploits  (외부 봇의 `/.env`, `/config.json` 등 스캔 차단)

**SSL 탭**
- SSL Certificate: **Request a new SSL Certificate**
- ✅ Force SSL  ✅ HTTP/2 Support
- 이메일 + Let's Encrypt 약관 동의 → **Save**

Save 시 Let's Encrypt 가 외부 80포트로 도메인 검증 → 성공하면 인증서 발급 완료.

---

## 5. 발생한 문제와 해결 (트러블슈팅 로그)

순서대로 4개의 별개 문제가 드러났다. 증상이 같은 502여도 **출처(Server 헤더)** 로 구분한다.

### 함정 1 — SSL 발급 실패 (외부 80/443 미연결)
- 증상: NPM 에서 인증서 발급이 안 됨. LAN 에서 80/443 닫힘.
- 원인: NPM 이 80/443이 아닌 41537/41391에 매핑됨 + 공유기 포워딩 부재.
- 해결: §3 포워딩(외부 80→41537, 443→41391).

### 함정 2 — HTTPS 전체 502 (`Server: openresty`)
- 증상: HTTP는 301 리다이렉트, HTTPS는 502. 인증서는 정상(핸드셰이크 성공).
- 원인: 프록시 호스트 **업스트림 Scheme이 `https`** → NPM이 평문 HTTP 포트(8080)에
  TLS로 접속 → `SSL_do_handshake() failed ... wrong version number`.
  ```
  # /data/logs/proxy-host-4_error.log
  ... SSL handshaking to upstream, upstream: "https://192.168.0.101:8080/"
  ```
- 해결: 프록시 호스트 Scheme을 **`http`** 로 변경.

### 함정 3 — 백엔드 크래시 루프 (`/api` 502, `Server: nginx/1.31.2`)
- 증상: 메인 페이지는 200인데 `/api/...` 만 502. 502 출처가 NPM이 아닌 **프론트 nginx**.
  백엔드 컨테이너 STATUS = `Restarting`.
- 원인: 백엔드 부팅 시 `db.apply_schema()` 의 **실행 순서 버그**.
  `SCHEMA` 문자열 안의 `CREATE INDEX idx_profiles_owner ON scoring_profiles(owner)` 가
  **레거시 DB(=owner 컬럼 없는 기존 테이블)** 에서 먼저 실행되어
  `sqlite3.OperationalError: no such column: owner` 발생 → `executescript` 전체 실패 →
  그 뒤에 있던 `ALTER TABLE scoring_profiles ADD COLUMN owner` 보강에 도달조차 못함.
- 해결: 인덱스 생성을 `SCHEMA` 에서 빼서 **ALTER(컬럼 보강) 이후**로 이동
  ([backend/app/db.py](../../backend/app/db.py) `apply_schema`).
  ```python
  # SCHEMA 끝의 CREATE INDEX idx_profiles_owner ... 줄 제거,
  # apply_schema() 의 ALTER 마이그레이션 직후로 이동:
  conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_owner ON scoring_profiles(owner)")
  ```
  적용: 코드가 이미지에 빌드되므로 **재빌드 필요**.
  ```bash
  docker compose up -d --build backend
  ```
  > 빠른 임시 복구(재빌드 없이): `sqlite3 data/app.sqlite "ALTER TABLE scoring_profiles ADD COLUMN owner TEXT;"` 후 백엔드 재시작.

### 함정 4 — 백엔드 정상인데도 `/api` 502 (옛 IP 캐싱)
- 증상: 백엔드 로그 `Uvicorn running ...` 정상인데 프론트는 계속 502.
- 원인: 프론트 nginx `proxy_pass http://backend:8000/;` 는 **정적 resolve** →
  설정 로드 시점의 백엔드 IP 를 캐싱. 백엔드를 재빌드/재생성하면 컨테이너 IP 가 바뀌어
  프론트가 옛 IP 로 계속 접속.
- 해결: **프론트엔드 컨테이너 재시작**(재resolve).
  ```bash
  docker restart dim_wishlist_hub-frontend-1
  ```
  > 규칙: **백엔드를 재생성하면 프론트엔드도 재시작**한다.
  > 한 번에: `docker compose up -d --force-recreate`(의존성 순서로 프론트가 새 IP 획득).

---

## 6. OAuth 로그인 (외부 HTTPS 대응)

내부 구간이 HTTP여도 **사용자에게 보이는 주소는 HTTPS 도메인**이므로,
OAuth 콜백/리다이렉트/쿠키를 도메인 기준으로 맞춰야 한다.

### `.env` 변경
```diff
- BUNGIE_OAUTH_REDIRECT_URI=http://localhost:8080/api/auth/bungie/callback
+ BUNGIE_OAUTH_REDIRECT_URI=https://muir20.ddns.net/api/auth/bungie/callback
- FRONTEND_URL=http://localhost:8080
+ FRONTEND_URL=https://muir20.ddns.net
+ SESSION_COOKIE_SECURE=1          # https 에서만 전송되는 Secure 쿠키
```
적용: env_file 은 컨테이너 시작 시 로드 → **재생성 + 프론트 재시작**(함정 4).
```bash
docker compose up -d --force-recreate backend
docker restart dim_wishlist_hub-frontend-1
```

### Bungie 개발자 포털 (사용자 수동)
- bungie.net/developer → 앱(client_id `53170`) → **Redirect URL**
  = `https://muir20.ddns.net/api/auth/bungie/callback`
- 등록값과 `BUNGIE_OAUTH_REDIRECT_URI` 가 **글자 단위로 정확히 일치**해야 함
  (http/https, 끝 슬래시, 경로). 불일치 시 Bungie 가 `redirect_uri mismatch` 거부.
- Bungie 는 콜백 URL 1개만 허용 → 도메인으로 바꾸면 `localhost` 로컬 로그인은 불가.

---

## 7. 검증

```powershell
# 메인 페이지 (200)
Invoke-WebRequest https://muir20.ddns.net -UseBasicParsing -MaximumRedirection 0

# 로그인 진입 (307 → bungie.net OAuth Authorize)
Invoke-WebRequest https://muir20.ddns.net/api/auth/bungie/login -UseBasicParsing -MaximumRedirection 0

# 콜백 (code 없이 호출 시 422 = 엔드포인트 도달·검증 정상)
Invoke-WebRequest https://muir20.ddns.net/api/auth/bungie/callback -UseBasicParsing -MaximumRedirection 0
```

**최종(브라우저)**: `https://muir20.ddns.net` → 로그인 → Bungie 승인 →
`https://muir20.ddns.net/?connected=1` 복귀 + 세션 쿠키 설정되면 완료.

진단 명령(NAS):
```bash
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
sudo docker logs --tail 40 dim_wishlist_hub-backend-1
sudo docker exec jc21_nginx-proxy-manager-1 sh -c "tail -n 20 /data/logs/proxy-host-*_error.log"
```

---

## 8. 체크리스트 (재현/이관 시)

- [ ] DDNS → 공인 IP 일치 확인
- [ ] 공유기 80→41537, 443→41391 포워딩
- [ ] 외부 80포트 개방 확인(LG U+ 차단 여부)
- [ ] NPM 프록시 호스트: Scheme=`http`, → 192.168.0.101:8080, Block Common Exploits
- [ ] SSL: Let's Encrypt 발급 + Force SSL + HTTP/2
- [ ] `.env`: REDIRECT_URI / FRONTEND_URL = 도메인, SESSION_COOKIE_SECURE=1
- [ ] Bungie 포털 Redirect URL = 도메인 콜백
- [ ] 백엔드 재생성 후 **프론트엔드 재시작**
- [ ] 브라우저 로그인 왕복 성공
