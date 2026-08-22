# Запуск плавающего виджета Джарвиса поверх рабочего стола.
# Требует поднятый фронтенд (localhost:5173) и бэкенд (localhost:8420) -
# тот же самый Nexus OS, что и в браузере, просто в отдельном окошке.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$root\node_modules\.bin\electron.cmd" $root