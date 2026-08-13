# Ручной запуск голосового сервера OmniVoice. Не входит в start_all.ps1
# намеренно: держит в видеопамяти ~3.3 ГБ из 4 просто сидя без дела, пока
# бот и веб-чат по умолчанию говорят через edge-tts. Запускать, когда
# захочется опробовать локальный голос — модель уже скачана.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Start-Process -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList "server.py" `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$root\..\voice_engine_stdout.log" `
    -RedirectStandardError "$root\..\voice_engine_stderr.log"

Write-Host "OmniVoice запускается — модель грузится в видеопамять, минуту-другую молчит."
Write-Host "Чтобы включить его для живого голоса: NEXUS_TTS_ENGINE=omnivoice в .env, затем перезапустить бэкенд."
Write-Host "Проверить готовность: curl http://127.0.0.1:8421/health"
