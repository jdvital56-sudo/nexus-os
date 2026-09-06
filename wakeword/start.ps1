# Ручной запуск сервера слова-будильника «Джарвис» (Vosk, офлайн, для
# плавающего виджета).
#
# 07.09.2026: будильник ТЕПЕРЬ входит в start_all.ps1 и поднимается сам —
# фаундер опробовал его (3580 распознаваний с 19.08 по 05.09) и решил
# оставить. Этот скрипт остаётся для ручного запуска, когда сторож не
# поднят: отладить, перезапустить отдельно, посмотреть вывод.
#
# Условие включения: сервер больше не пишет распознанную речь в лог.

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