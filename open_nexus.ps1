# Открыть Nexus OS одним двойным кликом. Если бэкенд/фронтенд не подняты —
# сначала поднимает их, потом открывает браузер. Вызывается из ярлыка на
# рабочем столе через open_nexus.vbs (тот запускает это скрыто, без консоли).

$root = "C:\Users\Вадим\projects\nexus-os"

function Test-Port($port) {
    (Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $port }) -ne $null
}

if (-not (Test-Port 8420)) {
    Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
        -ArgumentList "-m","uvicorn","backend.main:app","--host","127.0.0.1","--port","8420" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput "$root\backend_stdout.log" `
        -RedirectStandardError "$root\backend_stderr.log"
}

if (-not (Test-Port 5173)) {
    Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev" `
        -WorkingDirectory "$root\frontend" -WindowStyle Hidden `
        -RedirectStandardOutput "$root\frontend_stdout.log" `
        -RedirectStandardError "$root\frontend_stderr.log"
}

# Бота здесь агрессивно не поднимаем: у него свой замок на один экземпляр
# (core/singleton.py), но лишний Start-Process всё равно тратит секунду
# на проверку и выход — не страшно, но и незачем делать это при каждом
# клике по иконке. Наблюдатель в start_all.ps1 и так следит за ним.

Start-Sleep -Seconds 3

# Найдено 19.08.2026: у протокола http:// в реестре нет UserChoice (только
# у https), а Start-Process на голый URL идёт через DelegateExecute —
# фаундер жаловался, что клик по ярлыку «ничего не открывает». На деле
# либо открывалась фоновая вкладка без переключения фокуса (незаметно),
# либо резолвинг URL из скрытого процесса вёл себя не так, как из
# интерактивного. Зовём Chrome напрямую, отдельным окном — так результат
# виден сразу, без гадания про ассоциации протоколов и фокус окна.
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (Test-Path $chrome) {
    Start-Process -FilePath $chrome -ArgumentList "--new-window", "http://localhost:5173/personas"
} else {
    Start-Process "http://localhost:5173/personas"
}
