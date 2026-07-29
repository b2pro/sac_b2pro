# Sobe o ambiente de desenvolvimento completo:
# Postgres + backend (container com migrate/seed automaticos e hot-reload) + frontend (Vite dev).
# Para parar os containers depois: docker compose down

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

docker compose up -d --build db minio minio-init backend worker
if ($LASTEXITCODE -ne 0) {
    Write-Host "Falha ao subir os containers."
    exit 1
}

Write-Host "Aguardando o backend responder em http://localhost:8000/api/health ..."
$deadline = (Get-Date).AddSeconds(90)
$ok = $false
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}

if (-not $ok) {
    Write-Host "Backend nao respondeu em 90s. Ultimos logs:"
    docker compose logs --tail 50 backend
    exit 1
}

Write-Host ""
Write-Host "Ambiente de dev no ar:"
Write-Host "  API:         http://localhost:8000/api/health"
Write-Host "  Frontend:    http://localhost:5173 (subindo agora)"
Write-Host "  Super admin: admin@b2pro.com / admin-dev-12345 (slug vazio no login)"
Write-Host "  Parar containers: docker compose down"
Write-Host ""

Set-Location frontend
pnpm dev
