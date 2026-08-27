# Push local main to YOUR fork only (chaohuize24/device-models).
# Does NOT modify YueyaoZhu/device-models (upstream is fetch-only unless you push upstream explicitly).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Checking GitHub connectivity..." -ForegroundColor Cyan
try {
    $tcp = Test-NetConnection github.com -Port 443 -WarningAction SilentlyContinue
    if (-not $tcp.TcpTestSucceeded) {
        Write-Host "Cannot reach github.com:443. Check VPN/proxy/firewall, then retry." -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Network check failed. Ensure you can open https://github.com in a browser." -ForegroundColor Red
    exit 1
}

Write-Host "Remotes:" -ForegroundColor Cyan
git remote -v

$originUrl = (git remote get-url origin 2>$null)
if ($originUrl -notmatch "chaohuize24/device-models") {
    Write-Host "origin is not chaohuize24/device-models. Aborting." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "If https://github.com/chaohuize24/device-models does not exist yet:" -ForegroundColor Yellow
Write-Host "  1. Open https://github.com/YueyaoZhu/device-models"
Write-Host "  2. Click Fork -> create under chaohuize24"
Write-Host "  3. Run this script again"
Write-Host ""

git status -sb
git push -u origin main

Write-Host ""
Write-Host "Done. Share with colleagues:" -ForegroundColor Green
Write-Host "  https://github.com/chaohuize24/device-models"
