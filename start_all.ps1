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

# OmniVoice: свой venv (конфликтует зависимостями с бэкендом, см. tts.py),
# грузит модель в память при старте — минуту-другую молчит, это нормально.
# Не критичен для остальной системы: если не поднимется, голос просто
# останется на движке edge (NEXUS_TTS_ENGINE в .env).
if (Test-Path "$root\voice_engine\.venv\Scripts\python.exe") {
    Set-Location "$root\voice_engine"
    Start-Process -FilePath "$root\voice_engine\.venv\Scripts\python.exe" -ArgumentList "server.py" `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$root\voice_engine_stdout.log" `
        -RedirectStandardError "$root\voice_engine_stderr.log"
}
