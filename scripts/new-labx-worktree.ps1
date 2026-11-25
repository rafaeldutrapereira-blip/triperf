<#
.SYNOPSIS
  Crea un worktree de git para correr una pila de LabX en paralelo (WORKTREES, BUILD 414).

.DESCRIPTION
  Crea C:\Users\rafae\projects\LabX-<Pila> desde -Base con la rama pila-<Build>-<Pila>
  y prepara el arbol (ver docs: REPORT-labx-worktrees.md):
    - Python: se usa el Python del sistema (sin venv). El repo NO esta instalado como
      paquete (no hay pip -e), asi que `import api` resuelve contra el cwd = el worktree.
      La preparacion lo comprueba y falla si `api` apunta a otro arbol.
    - No se copia .env ni data/ (secretos / BD de la PC): los tests y el E2E gate usan
      BD temporal y sus propias credenciales.
  Si el worktree (carpeta) o la rama ya existen, falla SIN borrar nada.
  Nunca hace push.

.EXAMPLE
  .\scripts\new-labx-worktree.ps1 -Pila evals -Build 415 -Base 0107261
#>
param(
  [Parameter(Mandatory = $true)][string]$Pila,
  [Parameter(Mandatory = $true)][int]$Build,
  [Parameter(Mandatory = $true)][string]$Base,
  [string]$Repo = '',
  [string]$ParentDir = ''
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Repo) { $Repo = Split-Path -Parent $here }
if (-not $ParentDir) { $ParentDir = Split-Path -Parent $Repo }

function Fail($msg) { Write-Error "new-labx-worktree: $msg"; exit 1 }
function Invoke-GitChecked { & git -C $Repo @args; if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') fallo ($LASTEXITCODE)" } }

if ($Pila -notmatch '^[a-z0-9][a-z0-9-]*$') { Fail "nombre de pila invalido '$Pila' (usa minusculas, digitos y guiones)" }

$branch = "pila-$Build-$Pila"
$path   = Join-Path $ParentDir "LabX-$Pila"

if (Test-Path -LiteralPath $path) { Fail "ya existe la carpeta $path (no se borra nada)" }
& git -C $Repo show-ref --verify --quiet "refs/heads/$branch"
if ($LASTEXITCODE -eq 0) { Fail "ya existe la rama $branch (no se borra nada)" }
$registered = (& git -C $Repo worktree list --porcelain) -join "`n"
if ($registered.ToLower().Contains($path.Replace([string][char]92, '/').ToLower())) { Fail "git ya registra un worktree en $path" }

$sha = (& git -C $Repo rev-parse --verify --quiet "$Base^{commit}")
if ($LASTEXITCODE -ne 0 -or -not $sha) { Fail "la base '$Base' no resuelve a un commit" }

Invoke-GitChecked worktree add --quiet -b $branch $path $sha | Out-Null

# --- preparar el arbol -------------------------------------------------------
$py = (Get-Command python -ErrorAction Stop).Source
Push-Location $path
try { $apiFile = (& $py -c "import os,api;print(os.path.dirname(os.path.dirname(os.path.realpath(api.__file__))))") } finally { Pop-Location }
$want = (Resolve-Path -LiteralPath $path).Path
if ($apiFile.Trim().TrimEnd('\') -ne $want.TrimEnd('\')) {
  Write-Warning "import api resuelve a '$apiFile', no al worktree '$want'. Hay una instalacion -e del repo en el Python del sistema: desinstalala o usa un venv."
  exit 1
}
$deps = & $py -c "import fastapi,sqlalchemy,alembic,pytest,uvicorn;print('ok')" 2>&1
if ($deps -notmatch 'ok') {
  Write-Warning "faltan dependencias en el Python del sistema: pip install -r requirements-api.txt"
  exit 1
}

Write-Output "BRANCH=$branch BASE=$sha"
Write-Output $want
