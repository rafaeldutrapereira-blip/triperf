<#
.SYNOPSIS
  Junta a main la rama de una pila verificada y limpia su worktree (WORKTREES, BUILD 414).

.DESCRIPTION
  Dado -Pila, -Build y -Sha (el SHA verificado de la punta de la pila):
    1. exige que el repo principal este en main, sin cambios en archivos rastreados;
    2. exige que la rama pila-<Build>-<Pila> apunte EXACTAMENTE a -Sha y que su
       worktree no tenga cambios sin commitear en archivos rastreados;
    3. merge fast-forward si main es ancestro de la rama; si no, merge --no-ff con
       mensaje "merge:pila-<Build>-<Pila>";
    4. verifica el resultado: ff => HEAD == Sha; merge => 2do padre de HEAD == Sha;
    5. borra el worktree y la rama (solo si 1-4 pasaron).
  NUNCA hace push: el push lo hace Pocoyo por SSH con el ok de Rafael.
  Ante cualquier fallo antes del merge no se toca nada; si el merge deja conflicto se
  aborta (git merge --abort) y se reporta.
#>
param(
  [Parameter(Mandatory = $true)][string]$Pila,
  [Parameter(Mandatory = $true)][int]$Build,
  [Parameter(Mandatory = $true)][string]$Sha,
  [string]$Repo = '',
  [string]$ParentDir = ''
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Repo) { $Repo = Split-Path -Parent $here }
if (-not $ParentDir) { $ParentDir = Split-Path -Parent $Repo }
function Fail($msg) { Write-Error "merge-labx-worktree: $msg"; exit 1 }

$branch = "pila-$Build-$Pila"
$path   = Join-Path $ParentDir "LabX-$Pila"

$cur = (& git -C $Repo rev-parse --abbrev-ref HEAD).Trim()
if ($cur -ne 'main') { Fail "el repo principal esta en '$cur', debe estar en main" }
$dirty = & git -C $Repo status --porcelain --untracked-files=no
if ($dirty) { Fail "main tiene cambios sin commitear en archivos rastreados:`n$dirty" }

$full = (& git -C $Repo rev-parse --verify --quiet "$Sha^{commit}")
if ($LASTEXITCODE -ne 0) { Fail "el SHA '$Sha' no existe" }
$tip = (& git -C $Repo rev-parse --verify --quiet "refs/heads/$branch")
if ($LASTEXITCODE -ne 0) { Fail "no existe la rama $branch" }
if ($tip.Trim() -ne $full.Trim()) { Fail "la rama $branch apunta a $tip, no al SHA verificado $full (alguien commiteo despues de verificar)" }
if (-not (Test-Path -LiteralPath $path)) { Fail "no existe el worktree $path" }
$wtDirty = & git -C $path status --porcelain --untracked-files=no
if ($wtDirty) { Fail "el worktree tiene cambios sin commitear:`n$wtDirty" }

& git -C $Repo merge-base --is-ancestor main $branch
$ff = ($LASTEXITCODE -eq 0)
if ($ff) {
  & git -C $Repo merge --ff-only $branch | Out-Null
} else {
  & git -C $Repo merge --no-ff -m "merge:$branch" $branch | Out-Null
}
if ($LASTEXITCODE -ne 0) {
  & git -C $Repo merge --abort 2>$null
  Fail "el merge de $branch fallo (conflicto); se aborto, main intacta"
}

$head = (& git -C $Repo rev-parse HEAD).Trim()
if ($ff) { $got = $head } else { $got = (& git -C $Repo rev-parse "HEAD^2").Trim() }
if ($got -ne $full.Trim()) {
  Fail "verificacion post-merge fallo: esperado $full, obtenido $got (HEAD=$head). NO se borro worktree ni rama."
}

& git -C $Repo worktree remove --force $path
if ($LASTEXITCODE -ne 0) { Fail "merge ok (HEAD=$head) pero no pude borrar el worktree $path" }
& git -C $Repo branch -d $branch | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "merge ok (HEAD=$head) pero no pude borrar la rama $branch" }

$mode = if ($ff) { 'fast-forward' } else { 'merge' }
Write-Output "MERGED $branch ($mode) HEAD=$head"
