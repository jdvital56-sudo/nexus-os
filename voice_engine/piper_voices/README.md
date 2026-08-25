# Голоса Piper

Локальный синтез речи. Сами файлы моделей в git не хранятся — по 61 МБ каждый.

## Модели переехали (25.08.2026)

Голоса лежат в **`~/.nexsys/piper_voices`**, а не в этой папке. Причина: их
держит в памяти уже не только бэкенд, но и общий сервис голоса
(`voice_engine/piper_server.py`), а рабочих деревьев на одном проекте
бывает три сразу — копия по 180 МБ в каждом не нужна никому, и сервис не
должен зависеть от того, из какого дерева его запустили. `~/.nexsys` — то
самое место, где у Nexus OS лежат общие для всех деревьев данные.

Эта папка осталась запасной: и бэкенд, и сервис смотрят сначала в
`~/.nexsys/piper_voices`, потом сюда. Путь можно задать прямо —
`PIPER_VOICES_DIR`.

## Зачем

Переключено с edge-tts 24.08.2026 после замеров на этой машине:

| Движок | Первый байт звука | Разброс |
|---|---|---|
| edge-tts (серверы Microsoft) | 2.4 / 3.7 / **37.4** сек | непредсказуемый, сетевой |
| piper (этот компьютер) | 0.41–0.66 сек, медиана 0.55 | 0.26 сек |

Плюс Piper работает без интернета.

## Как скачать

```powershell
$base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU"
foreach ($v in "dmitri", "irina", "ruslan") {
    curl.exe -sL -o "ru_RU-$v-medium.onnx"      "$base/$v/medium/ru_RU-$v-medium.onnx"
    curl.exe -sL -o "ru_RU-$v-medium.onnx.json" "$base/$v/medium/ru_RU-$v-medium.onnx.json"
}
```

Доступные русские голоса: `denis`, `dmitri`, `irina` (женский), `ruslan`.
Полный список языков — huggingface.co/rhasspy/piper-voices

## Известная ловушка Windows

Нативный espeak-ng внутри Piper не читает пути с кириллицей (у этой машины
имя пользователя «Вадим») — падает с `Illegal byte sequence`. Обходится
коротким DOS-именем пути, см. `_piper_short_path` в `backend/services/tts.py`.
Та же ловушка была у Vosk, см. `wakeword/server.py`.
