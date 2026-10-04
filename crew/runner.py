"""Агентный цикл: модель просит инструмент — мы выполняем — она продолжает.

Три потолка, и все три обязательны. Автор разобранного видео жалуется прямым
текстом: «его надо уметь вовремя остановить, иначе можно за анализ одного
бренда засесть на день». Потолок итераций у неё виден (`iteration 4/60`), а
вот потолков времени и денег — нет, и именно поэтому её агент способен
работать день. Здесь:

- итерации (`MAX_ITERATIONS`) — от зацикливания;
- время (`MAX_WALL_SECONDS`) — от одного повисшего вызова;
- деньги (`MAX_RUN_USD`) — от прогона, который съест дневной лимит целиком.

Останов по любому из трёх — не ошибка, а нормальный исход: агент обязан
отдать то, что успел, и честно сказать, где остановился.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

import httpx

from . import config, handoff, lessons, prompts
from .tools import ToolContext, execute, specs_for
from .workspace import Workspace

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 180.0

# Провайдеры, говорящие на протоколе OpenAI. Остальные (Anthropic, Gemini)
# описывают инструменты своим форматом — для них здесь ветки нет, и это
# сознательно: три формата ради движка, который ещё не выбран, — работа в
# стол. Смена провайдера упрётся в понятную ошибку, а не в молчаливый сбой.
OPENAI_COMPATIBLE = {"openai", "deepseek", "ollama"}


class EngineNotReady(RuntimeError):
    """Движок не настроен так, чтобы команда могла работать."""


# Провайдер и ключ для команды. Отдельно от общих настроек Nexus OS
# намеренно: там `NEXSYS_LLM_PROVIDER=ollama`, и переключать его глобально
# значило бы сменить движок всем персонам Пантеона разом. Команде нужна
# модель посильнее локальной 8B, остальному — как настроено.
#
# Ключ ищем под несколькими именами. Причина конкретная: `backend/core/
# config.py` читает только `NEXSYS_LLM_API_KEY`, а реальные ключи лежат в
# .env под короткими именами (`DEEPSEEK_API_KEY` и т.д.) — и молча не
# подхватываются. Ровно от этой болезни в том же файле написан `env_any`,
# но к главному движку его не применили.
_KEY_NAMES = {
    "deepseek": ("NEXSYS_LLM_API_KEY", "DEEPSEEK_API_KEY"),
    "openai": ("NEXSYS_LLM_API_KEY", "OPENAI_API_KEY"),
    "ollama": (),
}

_DEFAULT_BASE = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434",
}

_DEFAULT_MODEL = {
    # Имя по официальной документации (сверено 24.09.2026). Старое
    # deepseek-chat пока принимается, но это наследие, а не обещание.
    "deepseek": "deepseek-flash",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.1:8b",
}


class CrewEngine:
    """Настройки модели для команды. Совместим с тем, что ждёт раннер."""

    def __init__(self) -> None:
        import os

        self.provider = (os.getenv("CREW_LLM_PROVIDER") or "deepseek").strip().lower()
        self.model = os.getenv("CREW_LLM_MODEL") or _DEFAULT_MODEL.get(self.provider, "")
        self.base_url = os.getenv("CREW_LLM_BASE_URL") or _DEFAULT_BASE.get(self.provider, "")
        self.api_key = ""
        for name in _KEY_NAMES.get(self.provider, ()):
            value = os.getenv(name, "").strip()
            if value:
                self.api_key = value
                break


def get_engine():
    """Движок команды, уже проверенный. Бросает `EngineNotReady`, если нельзя."""
    engine = CrewEngine()
    check_engine(engine)
    return engine


def completions_url(llm) -> str:
    """Адрес chat-completions с учётом провайдера.

    Ollama слушает `http://localhost:11434`, а OpenAI-совместимый вход у неё
    лежит под `/v1`. Без этого запрос уходил бы на несуществующий путь и
    падал бы с 404 — то есть система выглядела бы сломанной по неочевидной
    причине. Найдено живой проверкой: движком по умолчанию на этой машине
    оказалась именно ollama, а не DeepSeek.
    """
    # getattr, а не `llm.provider`: у тестовых дублёров LLM этого поля может
    # не быть вовсе — та же оговорка стоит в `backend/services/tools.py`.
    base = (llm.base_url or "").rstrip("/")
    if getattr(llm, "provider", "") == "ollama" and not base.endswith("/v1"):
        base = f"{base}/v1"
    return f"{base}/chat/completions"


def check_engine(llm) -> None:
    """Проверить движок до запуска, а не на первом сообщении человека."""
    if llm.provider not in OPENAI_COMPATIBLE:
        raise EngineNotReady(
            f"Движок «{llm.provider}» не умеет tool-calling в формате, который "
            "понимает команда. Поставь в .env NEXSYS_LLM_PROVIDER=deepseek "
            "(или openai) и ключ к нему."
        )
    if llm.provider != "ollama" and not llm.api_key:
        raise EngineNotReady(
            f"Для движка «{llm.provider}» не задан ключ. Положи его в .env: "
            "DEEPSEEK_API_KEY или OPENAI_API_KEY."
        )

# Повторы при обрыве связи. Живой прогон 24.09 поймал обрыв интернета
# посреди работы: одна секунда без сети — и бот отвечал «модель
# недоступна», хотя через десять секунд всё вернулось. Для системы,
# которая работает без присмотра, это недопустимо. Паузы растут: сеть,
# которая не вернулась за 2 секунды, редко возвращается через 3.
RETRY_DELAYS = (2.0, 5.0, 10.0, 20.0)

# Ответы сервера, после которых имеет смысл повторить: перегрузка и сбои.
# 400 и 401 не повторяем — там ошибка в запросе или ключе, и повтор
# только сожжёт время.
RETRY_STATUSES = {429, 500, 502, 503, 504}


async def post_with_retry(client, url: str, headers: dict, payload: dict, delays=None):
    """POST к модели с повторами на временных сбоях. Бросает, если не вышло.

    Паузы читаются при вызове, а не при определении функции: иначе значение
    вшивается навсегда и его нельзя поменять ни настройкой, ни в тесте —
    тест реально ждал по 2 и 5 секунд, этим и был пойман.
    """
    import asyncio

    delays = RETRY_DELAYS if delays is None else delays
    last: Exception | None = None
    for attempt in range(len(delays) + 1):
        try:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code in RETRY_STATUSES:
                raise httpx.HTTPStatusError(
                    f"сервер ответил {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(exc, httpx.HTTPStatusError) and status not in RETRY_STATUSES:
                raise
            last = exc
            if attempt < len(delays):
                logger.info("Сбой связи с моделью (%s), повтор через %.0f с", exc, delays[attempt])
                await asyncio.sleep(delays[attempt])
    assert last is not None
    raise last


# Сколько сообщений истории держим. Дальше — обрезаем середину: системный
# промпт и последние ходы важнее, чем то, что было двадцать вызовов назад.
HISTORY_LIMIT = 60


@dataclass
class RunResult:
    text: str
    iterations: int
    seconds: float
    cost_usd: float
    tools_used: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    stopped_by: str = ""
    """Пусто — модель закончила сама. Иначе: iterations | time | budget | error."""
    warnings: list[str] = field(default_factory=list)
    """Строки из чужих данных, похожие на команды, — показываются человеку кодом."""


class Runner:
    """Один агент, один разговор. История живёт на диске его песочницы."""

    def __init__(self, role_key: str, chat_id: str = "local") -> None:
        self.role = config.get_role(role_key)
        self.chat_id = str(chat_id)
        self.workspace = Workspace(self.role.key)
        self._history_path = self.workspace.root / "tmp" / "sessions" / f"{self.chat_id}.json"

    # --- история ---------------------------------------------------------

    def load_history(self) -> list[dict]:
        if not self._history_path.exists():
            return []
        try:
            return json.loads(self._history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("История %s повреждена, начинаю заново", self._history_path)
            return []

    def save_history(self, history: list[dict]) -> None:
        trimmed = history
        if len(trimmed) > HISTORY_LIMIT:
            # Голову оставляем: там первое задание человека, без него агент
            # забывает, что вообще делает. Режем середину.
            trimmed = trimmed[:6] + trimmed[-(HISTORY_LIMIT - 6):]
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        Workspace._atomic_write(
            self._history_path, json.dumps(trimmed, ensure_ascii=False).encode("utf-8")
        )

    def forget(self) -> None:
        if self._history_path.exists():
            self._history_path.unlink()

    # --- системный промпт -------------------------------------------------

    def system_prompt(self, project: str = "") -> str:
        base = prompts.load(self.role.key)
        # Уроки идут ПОСЛЕ роли и ПЕРЕД обстановкой — то есть ближе к концу,
        # где модель соблюдает написанное лучше всего. Это и есть механизм,
        # которым агент отличается сегодня от себя вчерашнего.
        learned = lessons.for_prompt(self.role.key)
        parts = [base]
        if learned:
            parts.append(learned)
        parts.append(self._live_context(project))
        return "\n\n".join(parts)

    def _live_context(self, project: str) -> str:
        """То, что меняется между запусками. Отдельно от промпта роли, чтобы
        не переписывать файл ради даты."""
        inbox = handoff.pending(self.role.key)
        inbox_line = (
            "\n".join(
                f"  - {item['handoff_id']} | проект `{item['meta'].get('project', '?')}` "
                f"| от {config.BY_KEY[item['meta']['from_role']].title}"
                for item in inbox
                if item["meta"].get("from_role") in config.BY_KEY
            )
            or "  (пусто)"
        )
        hands_to = ", ".join(
            f"{config.get_role(k).title} (`{k}`)" for k in self.role.hands_to
        ) or "никому — ты конец цепочки"

        return (
            "## Обстановка прямо сейчас\n\n"
            f"- Сегодня: {datetime.now().strftime('%Y-%m-%d, %A')}\n"
            # Относительный путь, а не абсолютный: полный путь несёт имя
            # пользователя Windows и уезжал бы в каждый запрос к модели.
            f"- Твоя рабочая папка: `{self.role.key}/workspace/` "
            "(пути в инструментах пиши относительно неё)\n"
            f"- Текущий проект: {project or 'не назван — спроси человека или найди в памяти'}\n"
            f"- Передаёшь работу: {hands_to}\n"
            f"- Непринятые передачи тебе:\n{inbox_line}\n\n"
            "Потолки прогона: "
            f"{config.MAX_ITERATIONS} обращений к инструментам, "
            f"{config.MAX_WALL_SECONDS // 60} минут, "
            f"${config.MAX_RUN_USD} расходов. Дойдя до любого — отдай то, что "
            "успел, и скажи, на чём остановился. Не начинай работу, которую "
            "заведомо не успеешь закончить: раздели на части и спроси."
        )

    # --- цикл ------------------------------------------------------------

    async def run(
        self,
        user_message: str,
        *,
        project: str = "",
        on_status: Callable[[str], Awaitable[None]] | None = None,
        on_tool: Callable[[str, str], None] | None = None,
        approve: Callable[[str, str], Awaitable[bool]] | None = None,
    ) -> RunResult:
        from backend.services import budget

        llm = get_engine()
        started = time.monotonic()
        context = ToolContext(
            role_key=self.role.key, project=project, approve=approve, on_tool=on_tool
        )

        history = self.load_history()
        history.append({"role": "user", "content": user_message})

        messages = [{"role": "system", "content": self.system_prompt(project)}, *history]
        tools = specs_for(self.role.key)

        used: list[str] = []
        usage_total: dict[str, int] = {}
        cost = 0.0
        stopped_by = ""
        answer = ""

        url = completions_url(llm)
        headers = {"Content-Type": "application/json"}
        if llm.api_key:
            headers["Authorization"] = f"Bearer {llm.api_key}"

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            for iteration in range(1, config.MAX_ITERATIONS + 1):
                elapsed = time.monotonic() - started
                if elapsed > config.MAX_WALL_SECONDS:
                    stopped_by = "time"
                    break
                if cost > config.MAX_RUN_USD:
                    stopped_by = "budget"
                    break

                if on_status:
                    await on_status(
                        f"⏳ Работаю — {int(elapsed // 60)} мин — "
                        f"итерация {iteration}/{config.MAX_ITERATIONS}"
                    )

                # На последней итерации инструменты убираем: модель обязана
                # ответить словами, а не просить ещё один вызов в пустоту.
                offer = tools if iteration < config.MAX_ITERATIONS else None
                payload: dict = {
                    "model": llm.model,
                    "messages": messages,
                    "temperature": 0.6,
                    "max_tokens": 4000,
                }
                if offer:
                    payload["tools"] = offer
                    payload["tool_choice"] = "auto"
                # deepseek-flash по умолчанию размышляет, а старое имя
                # deepseek-chat — та же модель без размышлений. Все оценки ролей
                # 24.09 сняты без них; к тому же с размышлениями DeepSeek ждёт,
                # что reasoning_content вернут в цепочке инструментов, а цикл
                # этого не делает. Проверено живыми запросами 25.09.
                if getattr(llm, "provider", "") == "deepseek":
                    payload["thinking"] = {"type": "disabled"}

                try:
                    response = await post_with_retry(client, url, headers, payload)
                except httpx.HTTPError as exc:
                    # Не выходим сразу: то, что агент успел сделать, и сам
                    # разговор должны сохраниться — иначе «продолжай» после
                    # восстановления сети начнёт с нуля.
                    logger.warning("Модель недоступна после повторов: %s", exc)
                    stopped_by = "network"
                    answer = (
                        "Связь с моделью пропала и не вернулась за минуту — "
                        f"остановился на шаге {iteration}. То, что успел "
                        "записать, сохранено. Напиши «продолжай», когда сеть "
                        "вернётся."
                    )
                    break

                data = response.json()
                for key, value in (data.get("usage") or {}).items():
                    if isinstance(value, int):
                        usage_total[key] = usage_total.get(key, 0) + value
                # Модель + инструменты (картинки). Раньше потолок видел только
                # токены — прогон с десятком кадров обходил его незаметно.
                cost = budget.estimate_cost(llm.model, usage_total) + context.spend_usd

                message = ((data.get("choices") or [{}])[0].get("message")) or {}
                calls = message.get("tool_calls") or []

                if not calls:
                    answer = message.get("content") or ""
                    messages.append({"role": "assistant", "content": answer})
                    break

                # Просьба модели обязана остаться в истории: без неё следующий
                # запрос отвергается — результат ссылается на вызов, которого
                # в разговоре нет.
                messages.append(message)
                for call in calls:
                    function = call.get("function") or {}
                    name = function.get("name") or ""
                    used.append(name)
                    output = await execute(context, name, function.get("arguments") or "{}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "content": output,
                        }
                    )
            else:
                stopped_by = "iterations"

        if stopped_by and not answer:
            answer = self._stop_notice(stopped_by, context)

        budget.record(llm.model, usage_total)
        self.save_history([m for m in messages[1:]])

        return RunResult(
            text=answer or "Модель вернула пустой ответ.",
            iterations=len([m for m in messages if m.get("role") == "assistant"]),
            seconds=time.monotonic() - started,
            cost_usd=round(cost, 6),
            tools_used=used,
            files=list(context.generated_files),
            stopped_by=stopped_by,
            warnings=list(context.warnings),
        )

    def _stop_notice(self, reason: str, context: ToolContext) -> str:
        made = "\n".join(f"- `{path}`" for path in context.generated_files) or "- ничего"
        why = {
            "iterations": f"дошёл до потолка в {config.MAX_ITERATIONS} обращений к инструментам",
            "time": f"дошёл до потолка в {config.MAX_WALL_SECONDS // 60} минут",
            "budget": f"дошёл до потолка расходов ${config.MAX_RUN_USD} за прогон",
        }.get(reason, reason)
        return (
            f"Остановился: {why}.\n\n"
            f"Что успел записать:\n{made}\n\n"
            "Это не значит, что работа сделана наполовину плохо — значит, она "
            "не влезла в один заход. Скажи, с какого места продолжить."
        )
