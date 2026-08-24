# Голоса Piper

Локальный синтез речи. Сами файлы моделей в git не хранятся — по 61 МБ каждый.

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
