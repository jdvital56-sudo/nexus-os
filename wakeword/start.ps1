# Ручной запуск сервера слова-будильника «Джарвис» (Vosk, офлайн, для
# плавающего виджета). Не входит в start_all.ps1 автоматически: держит
# микрофон непрерывно открытым — фаундер должен явно решить, что хочет
# фоновое прослушивание, не получать его молча вместе с остальным.
# Когда опробует и решит оставить — можно перенести сюда же, что и с
# OmniVoice.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = Split-Path -Parent $root

Start-Process -FilePath "$project\.venv\Scripts\python.exe" -ArgumentList "wakeword\server.py" `
    -WorkingDirectory $project `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$root\wakeword_stdout.log" `
    -RedirectStandardError "$root\wakeword_stderr.log"

Write-Host "Сервер слова-будильника запускается - модель Vosk грузится, секунда-другая."
Write-Host "Проверить: логи в wakeword\wakeword_stdout.log / wakeword_stderr.log"
Write-Host "Слушает ws://127.0.0.1:8422 - виджет подключается сам, если запущен Electron."