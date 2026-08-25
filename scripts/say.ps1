# Сказать вслух из любого места: терминала, скрипта, любого проекта.
#
#   .\scripts\say.ps1 "Сборка прошла"
#   .\scripts\say.ps1 "Готово" -Voice ru_RU-irina-medium
#   npm run build; .\scripts\say.ps1 "Сборка закончилась"
#
# Смысл: голос перестаёт быть функцией одной программы. Долгая команда в
# терминале может позвать в конце — и не надо сидеть и смотреть на неё.

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Text,

    [string]$Voice,

    # Отдать WAV файлом вместо того, чтобы говорить здесь
    [string]$OutFile
)

$ErrorActionPreference = "Stop"

$server = if ($env:PIPER_SERVER) { $env:PIPER_SERVER } else { "http://127.0.0.1:8424" }

$payload = @{ text = $Text }
if ($Voice) { $payload.voice = $Voice }
$body = [System.Text.Encoding]::UTF8.GetBytes(($payload | ConvertTo-Json))

$path = if ($OutFile) { "/say" } else { "/speak" }

try {
    $response = Invoke-WebRequest -Uri "$server$path" -Method Post `
        -ContentType "application/json; charset=utf-8" -Body $body `
        -UseBasicParsing -TimeoutSec 60
}
catch {
    Write-Host ""
    Write-Host "  Голос молчит: сервис не отвечает на $server" -ForegroundColor Yellow
    Write-Host "  Он поднимается вместе с остальным через start_all.ps1."
    Write-Host "  Вручную: .venv\Scripts\python.exe voice_engine\piper_server.py"
    Write-Host ""
    exit 1
}

if ($OutFile) {
    [System.IO.File]::WriteAllBytes($OutFile, $response.Content)
    Write-Host "  Записано: $OutFile"
}
