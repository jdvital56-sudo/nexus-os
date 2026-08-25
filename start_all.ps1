# Nexus OS - автозапуск и постоянный присмотр за бэкендом, ботом Тота
# и фронтендом. Не просто запускает один раз: Windows-автозагрузка
# срабатывает только при ВХОДЕ в систему, не при выходе из сна - если
# один из трёх процессов упадёт (сетевой сбой, что угодно), никто его
# больше не поднимет до следующего логина. 18.08.2026: именно так бот
# молчал четыре дня - упал ночью на сетевой ошибке, комп не
# перезагружался, автозагрузка не срабатывала снова.
#
# Поэтому этот скрипт не завершается: раз в 2 минуты проверяет, слушают
# ли порты бэкенда и фронтенда, и поднимает то, что упало. Пишет логи
# рядом с проектом.

$root = "C:\Users\Вадим\projects\nexus-os"
$checkEverySeconds = 120

function Test-Port($port) {
    (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $port }) -ne $null
}

function Start-Backend {
    Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
        -ArgumentList "-m","uvicorn","backend.main:app","--host","127.0.0.1","--port","8420" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput "$root\backend_stdout.log" `
        -RedirectStandardError "$root\backend_stderr.log"
}

function Start-Bot {
    Start-Process -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList "hermes\bot.py" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput "$root\hermes_stdout.log" `
        -RedirectStandardError "$root\hermes_stderr.log"
}

function Start-Frontend {
    Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev" `
        -WorkingDirectory "$root\frontend" -WindowStyle Hidden `
        -RedirectStandardOutput "$root\frontend_stdout.log" `
        -RedirectStandardError "$root\frontend_stderr.log"
}

# Общий голос Piper (25.08.2026) — один на всю машину, а не по копии в
# каждой программе. Держит модель в памяти, чтобы любой проект получал
# фразу за доли секунды. Модели лежат в ~/.nexsys/piper_voices, общих для
# всех рабочих деревьев, так что дерево запуска роли не играет.
function Start-Voice {
    Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
        -ArgumentList "voice_engine\piper_server.py" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput "$root\piper_server_stdout.log" `
        -RedirectStandardError "$root\piper_server_stderr.log"
}

# У бота нет своего порта - присматриваем по процессу, не по сети
function Test-Bot {
    (Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*hermes\bot.py*' }) -ne $null
}

Start-Sleep -Seconds 10  # дать сети и диску подняться после логина

while ($true) {
    if (-not (Test-Port 8420)) { Start-Backend; Start-Sleep -Seconds 5 }
    if (-not (Test-Bot)) { Start-Bot }
    if (-not (Test-Port 5173)) { Start-Frontend }
    if (-not (Test-Port 8424)) { Start-Voice }
    Start-Sleep -Seconds $checkEverySeconds
}

# OmniVoice сюда намеренно не входит: живой голос сейчас на Piper, а
# сервер OmniVoice держит в видеопамяти ~3.3 ГБ из 4 (вся карта) просто
# сидя без дела. Включать вручную через voice_engine\start.ps1, когда
# понадобится - модель уже скачана, повторно тянуть не придётся.