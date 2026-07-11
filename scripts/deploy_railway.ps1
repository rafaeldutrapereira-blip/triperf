# deploy_railway.ps1 — Deploy completo de LabX a Railway
# Ejecutar desde C:\Users\rafae\projects\LabX\
# Requiere: railway CLI instalado, .env.production completado

param(
    [string]$StripeKey,
    [string]$ResendKey
)

$ErrorActionPreference = "Stop"
$root = Split-Path $MyInvocation.MyCommand.Path -Parent | Split-Path -Parent

Write-Host "`n=== LabX Deploy a Railway ===" -ForegroundColor Cyan

# 1. Leer .env.production
$envFile = Join-Path $root ".env.production"
if (-not (Test-Path $envFile)) {
    Write-Error ".env.production no encontrado. Crea uno basado en .env.production.example"
    exit 1
}

$envVars = @{}
Get-Content $envFile | Where-Object { $_ -match "^[^#].*=.*" } | ForEach-Object {
    $parts = $_ -split "=", 2
    $k = $parts[0].Trim()
    $v = $parts[1].Trim()
    if (-not $v.StartsWith("<")) {
        $envVars[$k] = $v
    } else {
        Write-Warning "Variable sin completar: $k"
    }
}

# Override si se pasan como parámetros
if ($StripeKey) { $envVars["STRIPE_SECRET_KEY"] = $StripeKey }
if ($ResendKey)  { $envVars["RESEND_API_KEY"] = $ResendKey }

# 2. Verificar variables críticas
$required = @("JWT_SECRET", "FERNET_KEY", "STRIPE_SECRET_KEY", "RESEND_API_KEY", "STRIPE_PRICE_PRO", "STRIPE_PRICE_ELITE", "STRIPE_PRICE_COACH")
$missing = $required | Where-Object { -not $envVars.ContainsKey($_) -or $envVars[$_] -eq "" }
if ($missing) {
    Write-Error "Variables faltantes en .env.production: $($missing -join ', ')"
    exit 1
}

Write-Host "✓ Variables de entorno validadas" -ForegroundColor Green

# 3. Login (si no está logueado)
$whoami = railway whoami 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n→ Iniciando login Railway (se abrirá el navegador)..." -ForegroundColor Yellow
    railway login
}

# 4. Inicializar proyecto si no existe railway.json
Set-Location $root
$railwayJson = Join-Path $root "railway.json"
if (-not (Test-Path $railwayJson)) {
    Write-Host "`n→ Inicializando proyecto Railway..." -ForegroundColor Yellow
    railway init --name labx-coach
}

# 5. Agregar PostgreSQL si no existe
Write-Host "`n→ Verificando PostgreSQL plugin..." -ForegroundColor Yellow
railway add --plugin postgresql 2>&1 | Write-Host

# 6. Configurar variables de entorno en Railway
Write-Host "`n→ Configurando variables de entorno..." -ForegroundColor Yellow
foreach ($kv in $envVars.GetEnumerator()) {
    railway variables set "$($kv.Key)=$($kv.Value)" 2>&1 | Out-Null
    Write-Host "  SET $($kv.Key)" -ForegroundColor DarkGray
}
Write-Host "✓ Variables configuradas" -ForegroundColor Green

# 7. Deploy
Write-Host "`n→ Desplegando a Railway..." -ForegroundColor Yellow
railway up --detach

Write-Host "`n✓ Deploy iniciado." -ForegroundColor Green
Write-Host "  Ver logs: railway logs --tail" -ForegroundColor Cyan
Write-Host "  URL:      railway open" -ForegroundColor Cyan

# 8. Mostrar URL para webhook de Stripe
Start-Sleep -Seconds 5
$url = railway status 2>&1 | Select-String "https://"
Write-Host "`n=== Stripe Webhook ===" -ForegroundColor Yellow
Write-Host "Agrega este endpoint en dashboard.stripe.com → Developers → Webhooks:"
Write-Host "  URL: $url/api/stripe/webhook" -ForegroundColor White
Write-Host "  Eventos: customer.subscription.created, customer.subscription.updated, customer.subscription.deleted"
