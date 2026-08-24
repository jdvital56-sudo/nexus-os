# Отдельное рабочее дерево под одну сессию Claude Code.
#
# Зачем: несколько сессий в одном каталоге дерутся за файлы, и `git add -A`
# в одной утаскивает незакоммиченную работу другой (случилось 24.08.2026).
# Каждой сессии — свой каталог и своя ветка, тогда пересечься нечем.
#
# Данные (~/.nexsys) остаются ОБЩИМИ намеренно: это одна личная система с
# одной памятью, задачами и контентом. Разделять их — значит получить два
# разных Nexus OS. Запись в JSON защищена межпроцессным локом.
#
#   .\scripts\new-session.ps1 контент
#   .\scripts\new-session.ps1 голос
#
# В конце работы: закоммитить в своей ветке, влить в main, убрать дерево —
# как это сделать, скрипт печатает сам.

param(
    [Parameter(Mandatory = $true)]
    [string]$Name
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$slug = ($Name -replace '[^\w\-]', '-').ToLower()
$dir = Join-Path $root ".claude\worktrees\$slug"
$branch = "session/$slug"

if (Test-Path $dir) {
    Write-Host ""
    Write-Host "  Дерево '$slug' уже есть: $dir" -ForegroundColor Yellow
    Write-Host "  Откройте его или возьмите другое имя."
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "  Создаю дерево '$slug' на ветке $branch…"

git -C $root worktree add -b $branch $dir | Out-Null

# Секреты и ключи не в git — без них бэкенд не поднимется. Копируем, а не
# ссылаемся: сессия может править .env под свою задачу, не ломая соседям.
foreach ($file in @(".env", "credentials.json", "token.json")) {
    $src = Join-Path $root $file
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $dir $file)
        Write-Host "    скопирован $file"
    }
}

# node_modules — сотни мегабайт, копировать незачем. Junction на Windows
# делается без прав администратора, в отличие от симлинка.
$modulesSrc = Join-Path $root "frontend\node_modules"
$modulesDst = Join-Path $dir "frontend\node_modules"
if ((Test-Path $modulesSrc) -and -not (Test-Path $modulesDst)) {
    New-Item -ItemType Junction -Path $modulesDst -Target $modulesSrc | Out-Null
    Write-Host "    node_modules подключён ссылкой"
}

# Хук против `git add -A` копировать не нужно: git отдаёт рабочим деревьям
# каталог хуков главного репозитория, так что заслон действует и здесь.

Write-Host ""
Write-Host "  Готово: $dir" -ForegroundColor Green
Write-Host ""
Write-Host "  Дальше:"
Write-Host "    cd `"$dir`""
Write-Host "    ..\..\..\.venv\Scripts\python.exe -m pytest    # тесты, venv общий"
Write-Host ""
Write-Host "  Серверы (:8420 и :5173) поднимает ТОЛЬКО одна сессия за раз —"
Write-Host "  данные и расписание общие, вторая копия им только помешает."
Write-Host ""
Write-Host "  Когда закончите:"
Write-Host "    git -C `"$dir`" push -u origin $branch   # если нужен PR"
Write-Host "    git -C `"$root`" merge $branch          # или влить прямо в main"
Write-Host "    .\scripts\end-session.ps1 $slug         # убрать дерево"
Write-Host ""
