# 🚀 NEXSYS HERMES — AI Operating System

**Hermes Edition** — Полная интеграция с Telegram, ночная аналитика Dream Cadence, Пантеон персон, и бизнес-автоматизация.

---

## 🎯 Что это такое

NEXSYS Hermes — это мост между вашим мобильным устройством (Telegram) и ПК-средой разработки (Claude Code/Cursor). Система обеспечивает **сквозной контекст** 24/7.

### Основные возможности:

1. **Telegram Interface** — Управление системой через бота с телефона
2. **Голосовые команды** — Транскрибация через Google Gemini
3. **Пантеон Персон** — 5 специализированных AI-ролей
4. **Dream Cadence** — Ночная аналитика по 8 направлениям
5. **B2B Automation** — Поиск лидов через Apollo.io
6. **Calendar Integration** — Google Calendar + Gmail

---

## ⚡ Быстрая установка

```bash
# 1. Установить зависимости и создать рабочие папки
make install

# 2. Настроить .env (добавить API ключи)
nano .env

# 3. Запустить бота
python hermes/bot.py   # из корня проекта
```

### Ручная установка

```bash
# Все зависимости, включая Hermes, лежат в одном файле
pip install -r backend/requirements.txt
```

---

## 📋 Пошаговая настройка

### Шаг 1: Telegram Bot

1. Откройте Telegram, найдите **@BotFather**
2. Отправьте `/newbot`
3. Выберите имя (например, "My Hermes Assistant")
4. Выберите username (должен оканчиваться на `bot`)
5. Скопируйте полученный токен
6. Найдите **@UserInfobot** для получения вашего User ID
7. Добавьте в `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   TELEGRAM_ALLOWED_USER_ID=987654321
   ```

### Шаг 2: LLM Providers (Пантеон)

| Провайдер | Для чего | Получить ключ |
|-----------|----------|---------------|
| **DeepSeek** | Код, анализ (дешево) | https://platform.deepseek.com |
| **Google Gemini** | Аудио, мультимодальность | https://aistudio.google.com/app/apikey |
| **Anthropic Claude** | Сложные рассуждения | https://console.anthropic.com |
| **OpenAI** | Универсальный | https://platform.openai.com |

Добавьте в `.env`:
```bash
DEEPSEEK_API_KEY=sk-...
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
OLLAMA_BASE_URL=http://localhost:11434
```

Каждая персона ходит в свою модель: Architect и Philosopher — в Anthropic,
Labyrinth — в OpenAI, Orpheus — в DeepSeek, Mercury — в локальную Ollama.
Если ключа провайдера нет, персона откатывается на модель по умолчанию
(`NEXSYS_LLM_PROVIDER`), диалог при этом не ломается.

**Дневной потолок расходов** (обязателен до включения автопилота):
```bash
NEXUS_DAILY_LLM_BUDGET_USD=5
```
При превышении фоновые задачи (Dream Cadence, цикл Jarvis, извлечение
сущностей) останавливаются до полуночи UTC, а Telegram/веб/голос продолжают
работать с предупреждением. Потраченное за день лежит в `~/.nexsys/llm_spend.json`.

### Шаг 3: Apollo.io (B2B лиды)

1. Зарегистрируйтесь на https://www.apollo.io
2. Перейдите в Settings → API Keys
3. Создайте ключ
4. Добавьте в `.env`:
   ```
   APOLLO_API_KEY=your_apollo_key
   ```

### Шаг 4: Google Calendar (OAuth)

1. Откройте https://console.cloud.google.com
2. Создайте новый проект
3. Включите **Google Calendar API** и **Gmail API**
4. Создайте OAuth 2.0 credentials (Desktop app)
5. Скачайте `credentials.json` в корень проекта
6. Добавьте в `.env`:
   ```
   GOOGLE_CREDENTIALS_FILE=credentials.json
   GOOGLE_SCOPES=https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/gmail.compose
   ```

### Шаг 5: Obsidian Vault (База знаний)

1. Создайте папку для заметок (например, `/Users/username/Obsidian/Wiki/Hermes`)
2. Добавьте в `.env`:
   ```
   OBSIDIAN_VAULT_PATH=/Users/username/Obsidian/Wiki/Hermes
   HERMES_ARTIFACTS_PATH=/Users/username/Documents/Hermes
   ```

---

## 🎭 Пантеон Персон

Система автоматически выбирает персону на основе запроса:

| Персона | Модель | Когда используется |
|---------|--------|-------------------|
| **Mercury** | Llama 3.3 | Скрипты, cron, автоматизация |
| **Philosopher** | Claude Opus | Философия, глубокий анализ |
| **Labyrinth** | GPT-4/DeepSeek | Исследования, поиск информации |
| **Architect** | Claude 3.5 Sonnet | Написание кода, JSON структуры |
| **Orpheus** | DeepSeek | Общие вопросы (fallback) |

### Примеры:

```
"Напиши скрипт для..." → Mercury
"В чем смысл жизни?" → Philosopher  
"Найди информацию о..." → Labyrinth
"Создай JSON структуру..." → Architect
"Привет, как дела?" → Orpheus
```

---

## 🌙 Dream Cadence (Ночная аналитика)

Автоматически запускается в **3:00 AM**, анализирует 8 направлений:

1. **Cost Intelligence** — Расходы на API за 24 часа
2. **Conversation & Context Drift** — Потеря контекста в диалогах
3. **Skill Performance** — Эффективность скиллов (оценка 1-10)
4. **Memory Hygiene** — Какие воспоминания устарели
5. **Workflow Patterns** — Что можно автоматизировать
6. **Session Hygiene** — Закрытие зависших сессий
7. **External Opportunities** — Новые API, тренды AI
8. **Business Outcomes** — Прогресс к целям (%)

**Утренний бриф** отправляется в Telegram в **8:00 AM**.

### Настройка расписания:

```bash
# В .env (cron формат):
NIGHT_ANALYSIS_CRON=0 3 * * *  # Каждый день в 3:00

# Context compression (0.8 = баланс, 0.95 = агрессивное):
CONTEXT_COMPRESSION_THRESHOLD=0.8
```

---

## 💬 Команды Telegram бота

| Команда | Описание |
|---------|----------|
| `/start` | Запуск бота, приветствие |
| `/status` | Статус системы (API, сервисы) |
| `/persons` | Список доступных персон |
| `/brief` | Получить утренний бриф |
| `/help` | Справка по командам |

### Примеры запросов (без команд):

```
📝 Текст: "Найди 20 кровельных компаний в Техасе"
🎤 Голос: [Отправляете голосовое сообщение]
```

---

## 🔗 API Endpoints

Если используете REST API вместо Telegram:

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/apollo/search` | Поиск контактов/компаний |
| GET | `/api/apollo/person/{id}` | Детали контакта |
| POST | `/api/calendar/events` | Создать событие |
| GET | `/api/calendar/events` | Список событий |
| POST | `/api/chat` | Чат с LLM |
| POST | `/api/transcribe` | Транскрибация аудио |

---

## 📁 Структура проекта

```
nexus-os/
├── hermes/
│   └── bot.py              # Telegram бот (Hermes)
├── backend/
│   ├── agents/
│   │   ├── persona_manager.py   # Пантеон персон
│   │   └── dream_cadence.py     # Ночная аналитика
│   ├── services/
│   │   ├── llm.py               # LLM клиент (Gemini, OpenAI...)
│   │   ├── apollo_client.py     # Apollo.io интеграция
│   │   └── google_calendar.py   # Google Calendar/Gmail
│   ├── skills/                  # Скиллы агентов
│   └── core/
│       └── config.py            # Конфигурация из .env
├── Makefile                # make install / test / run / dev
├── artifacts/              # Сгенерированные файлы
├── credentials.json        # Google OAuth (создать вручную)
├── .env                    # Конфигурация (не коммитить!)
├── .env.example            # Шаблон конфигурации
└── README_HERMES.md        # Этот файл
```

---

## 🔐 Безопасность

### Принципы:

1. **Human-in-the-loop** — ИИ создает черновики писем, отправка только вручную
2. **Telegram Authorization** — Только ваш User ID имеет доступ к боту
3. **Minimal Privileges** — Ограниченные права для внешних API (только чтение/черновики)
4. **Secure Storage** — Токены в `.env`, никогда не в коде

### Проверка авторизации:

```python
# В bot.py
def _authorize_user(self, user_id: int) -> bool:
    if not self.allowed_user_id:
        return True  # Нет ограничений если не настроено
    return str(user_id) == str(self.allowed_user_id)
```

---

## 🛠️ Требования

- **Python** 3.10+
- **Telegram** аккаунт (для бота)
- **API ключи**:
  - DeepSeek или OpenAI (обязательно)
  - Google Gemini (для аудио)
  - Apollo.io (опционально, для B2B)
  - Google OAuth (опционально, для Calendar)

---

## 🚀 Использование

### Запуск бота:

```bash
python hermes/bot.py   # из корня проекта
```

Ожидайте сообщение:
```
🚀 Hermes Agent started. Listening for messages...
```

### Запуск Dream Cadence вручную:

```python
from backend.agents.dream_cadence import dream_cadence
import asyncio

asyncio.run(dream_cadence.nightly_job())
```

### Автоматический старт аналитики:

```python
from backend.agents.dream_cadence import start_dream_cadence
start_dream_cadence()  # Запускает планировщик
```

---

## 🧪 Тестирование

### Проверка Telegram бота:

1. Запустите: `python hermes/bot.py   # из корня проекта`
2. Откройте бота в Telegram
3. Отправьте `/start`
4. Ожидайте: "👋 Привет! Я Hermes, твой AI-ассистент."

### Проверка LLM:

```python
from backend.services.llm import LLMClient
import asyncio

llm = LLMClient()
response = asyncio.run(llm.generate_response("Привет, кто ты?"))
print(response)
```

### Проверка Apollo:

```python
from backend.services.apollo_client import ApolloClient
import asyncio

apollo = ApolloClient(api_key="your_key")
results = asyncio.run(apollo.search_companies("tech companies"))
print(results)
```

---

## 🐛 Troubleshooting

### Бот не отвечает:

```bash
# Проверьте токен в .env
echo $TELEGRAM_BOT_TOKEN

# Проверьте логи
tail -f logs/hermes.log
```

### Ошибка "Unauthorized":

- Убедитесь, что ваш Telegram User ID указан в `TELEGRAM_ALLOWED_USER_ID`
- Получите ID через @UserInfobot

### LLM не работает:

- Проверьте API ключ в `.env`
- Убедитесь, что ключ активен и есть баланс
- Проверьте лимиты API

### Dream Cadence не запускается:

```bash
# Проверьте расписание
echo $NIGHT_ANALYSIS_CRON

# Запустите вручную для теста
python -c "from backend.agents.dream_cadence import dream_cadence; import asyncio; asyncio.run(dream_cadence.nightly_job())"
```

---

## 📖 Дополнительные ресурсы

- [CONTRIBUTING.md](CONTRIBUTING.md) — Руководство по разработке
- [.env.example](.env.example) — Все переменные окружения
- [Official Telegram Bot API](https://core.telegram.org/bots/api)
- [Google Gemini Documentation](https://ai.google.dev/docs)
- [Apollo.io API Docs](https://developer.apollo.io/)

---

## 🎯 Следующие шаги

1. ✅ **Настроить API ключи** в `.env`
2. ✅ **Запустить бота**: `python hermes/bot.py   # из корня проекта`
3. ✅ **Протестировать команды** в Telegram
4. 🔲 **Настроить Obsidian Vault** для базы знаний
5. 🔲 **Включить Dream Cadence** для ночной аналитики
6. 🔲 **Добавить свои скиллы** в `backend/skills/`

---

**Создано по мотивам видео Hermes / Claude Code OS**

*Интеграция мобильного общения и ПК-среды через сквозной контекст 24/7*
