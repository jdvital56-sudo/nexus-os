# Убирает рабочее дерево сессии — но только если работа не потеряется.
#
#   .\scripts\end-session.ps1 контент
#
# Скрипт намеренно упрямый: сначала проверяет, что в дереве нет
# незакоммиченного, а его ветка влита в main. В этом проекте уже находилось
# заброшенное дерево с невлитым коммитом — если бы его снесли молча, работа
# исчезла бы вместе с ним.

param(
    [Parameter(Mandatory = $true)]
    [string]$Name,

    # Снести, даже если ветка не влита. Только когда работа точно не нужна.
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$slug = ($Name -replace '[^\w\-]', '-').ToLower()
$dir = Join-Path $root ".claude\worktrees\$slug"
$branch = "session/$slug"

if (-not (Test-Path $dir)) {
    Write-Host ""
    Write-Host "  Дерева '$slug' нет: $dir" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

$dirty = git -C $dir status --porcelain
if ($dirty -and -not $Force) {
    Write-Host ""
    Write-Host "  ОСТАНОВЛЕНО: в дереве есть незакоммиченное." -ForegroundColor Red
    Write-Host ""
    $dirty | ForEach-Object { Write-Host "    $_" }
    Write-Host ""
    Write-Host "  Закоммитьте или откажитесь от правок, потом повторите."
    Write-Host ""
    exit 1
}

$merged = $true
try {
    git -C $root merge-base --is-ancestor $branch main 2>$null
    $merged = ($LASTEXITCODE -eq 0)
} catch {
    $merged = $false
}

if (-not $merged -and -not $Force) {
    Write-Host ""
    Write-Host "  ОСТАНОВЛЕНО: ветка $branch не влита в main." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Что в ней есть, чего нет в main:"
    git -C $root log --oneline main..$branch | ForEach-Object { Write-Host "    $_" }
    Write-Host ""
    Write-Host "  Влить:      git -C `"$root`" merge $branch"
    Write-Host "  Или снести вместе с работой:  .\scripts\end-session.ps1 $slug -Force"
    Write-Host ""
    exit 1
}

git -C $root worktree remove $dir --force
if ($merged) {
    git -C $root branch -d $branch 2>$null | Out-Null
}

Write-Host ""
Write-Host "  Дерево '$slug' убрано." -ForegroundColor Green
Write-Host ""
