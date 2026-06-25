# LAN 공유용 방화벽 규칙 추가 — 반드시 "관리자 권한" PowerShell 에서 실행.
#   1) 시작 메뉴 → Windows PowerShell → 우클릭 → "관리자 권한으로 실행"
#   2) 이 스크립트 실행:  powershell -ExecutionPolicy Bypass -File scripts\allow-lan-8080.ps1
#
# 같은 LAN(로컬 서브넷)에서만 8080 인바운드를 허용한다(외부망 차단). 전제: docker-compose 가
# WEB_BIND=0.0.0.0 으로 8080 을 0.0.0.0 에 바인딩하고 있어야 한다(.env 참고).
# ⚠ 이 앱은 인증이 없으므로 같은 네트워크의 누구나 접근 가능 — 신뢰된 망에서만 사용할 것.

$ErrorActionPreference = 'Stop'
$name = 'DIM Wishlist Hub 8080 (LAN)'

if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) {
  Write-Host "이미 규칙이 있습니다: $name"
} else {
  New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 8080 -Profile Any -RemoteAddress LocalSubnet | Out-Null
  Write-Host "방화벽 규칙 추가 완료: TCP 8080 인바운드 허용(로컬 서브넷 전용)."
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '169.254*' -and $_.IPAddress -ne '127.0.0.1' } |
  Select-Object -First 1).IPAddress
Write-Host "이제 같은 네트워크의 기기에서 접속:  http://$ip`:8080"
