# Nexus OS — автозапуск бэкенда, бота Тота и фронтенда при входе в систему.
# Пишет логи рядом с проектом, ничего не выводит на экран (запускается скрыто).

$root = "C:\Users\Вадим\projects\nexus-os"
Set-Location $root

Start-Sleep -Seconds 10  # дать сети и диску подняться после логина

Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","backend.main:app","--host","127.0.0.1","--port","8420" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$root\backend_stdout.log" `
    -RedirectStandardError "$root\backend_stderr.log"

Start-Sleep -Seconds 5

Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
    -ArgumentList "hermes\bot.py" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$root\hermes_stdout.log" `
    -RedirectStandardError "$root\hermes_stderr.log"

Set-Location "$root\frontend"
Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$root\frontend_stdout.log" `
    -RedirectStandardError "$root\frontend_stderr.log"

# OmniVoice сюда намеренно не входит: живой голос сейчас на edge-tts, а
# сервер OmniVoice держит в видеопамяти ~3.3 ГБ из 4 (вся карта) просто
# сидя без дела. Включать вручную через voice_engine\start.ps1, когда
# понадобится — модель уже скачана, повторно тянуть не придётся.
