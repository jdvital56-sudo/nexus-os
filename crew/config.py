"""Реестр ролей и пути песочниц.

Раскладка папок намеренно повторяет ту, что видно в разобранном видео:
`<root>/<role>/workspace/docs/...`. Это не подражание — это делает переезд на
арендованный сервер операцией `rsync`, а не переписыванием путей. Когда
появится VPS, `NEXUS_CREW_ROOT=/srv/hermes` даст ровно `/srv/hermes/<role>/
workspace/`, как в оригинале.

Имена ролей — русские должности, по канону слоя «Работники». Проверка на
пересечение с существующим `AgentRole` (Строитель, Библиотекарь, Рецензент,
Исследователь, Монитор, Куратор, Джарвис) выполняется тестом, а не на глаз:
дважды названная сущность уже стоила этому проекту двух «Ра» и двух «Анубисов».
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Корень песочниц. На Windows — внутри проекта, на сервере задаётся переменной.
CREW_ROOT = Path(
    os.getenv("NEXUS_CREW_ROOT")
    or (Path(__file__).resolve().parent.parent / "crew_workspaces")
).resolve()

# Потолок итераций агентного цикла. В видео видно `iteration 4/60` — там 60.
# Столько же берём и мы: это не «сколько нужно», а «после скольких точно
# что-то пошло не так». Нижняя граница задаётся не здесь, а тем, что модель
# сама перестаёт звать инструменты.
MAX_ITERATIONS = int(os.getenv("NEXUS_CREW_MAX_ITERATIONS", "60"))

# Потолок времени на один прогон. Автор видео жалуется: «его надо уметь вовремя
# остановить, иначе можно за анализ одного бренда засесть на день». Потолок
# итераций от этого не спасает — один вызов веб-поиска может висеть минуты.
MAX_WALL_SECONDS = int(os.getenv("NEXUS_CREW_MAX_SECONDS", "900"))

# Потолок расходов на один прогон, в долларах. Дневной лимит уже есть в
# `backend/services/budget.py`; этот — про один зациклившийся запуск, который
# способен съесть дневной лимит целиком за десять минут.
MAX_RUN_USD = float(os.getenv("NEXUS_CREW_MAX_RUN_USD", "1.50"))


@dataclass(frozen=True)
class Role:
    """Одна роль: имя на экране, ключ на диске, права, промпт."""

    key: str
    """Технический ключ. Имя папки песочницы и имя файла промпта."""

    title: str
    """Как называется на экране и в Telegram. Русская должность."""

    tagline: str
    """Одна строка о том, что делает. Идёт в /start и в список команды."""

    tools: tuple[str, ...]
    """Белый список инструментов. Роль физически не видит остальные."""

    accepts_from: tuple[str, ...] = ()
    """От кого принимает handoff. Пустое — ни от кого, вход только от человека."""

    hands_to: tuple[str, ...] = ()
    """Кому передаёт. Пустое — конечная точка цепочки."""

    doc_root: str = "docs"
    """Подпапка проектной памяти внутри workspace."""

    env_token: str = ""
    """Имя переменной с токеном Telegram-бота этой роли."""

    extra_dirs: tuple[str, ...] = field(default=())
    """Папки, создаваемые при инициализации сверх стандартных."""


# Базовый набор файловых инструментов — есть у всех ролей без исключения.
# Это то, что отличает агента от бота на промпте: он читает и пишет своей
# памятью, а не помнит разговор.
_FILE_TOOLS = (
    "read_file",
    "write_file",
    "patch_file",
    "search_files",
    "list_dir",
    "session_search",
    "todo",
)

# Передача работы. Есть у всех, кроме конечных ролей без адресата.
_HANDOFF_TOOLS = ("submit_handoff", "inbox_list", "read_handoff", "accept_handoff")


ROLES: tuple[Role, ...] = (
    Role(
        key="marketer",
        title="Маркетолог",
        tagline="Разбирает бренд, конкурентов, аудиторию и боли. С него начинается проект.",
        tools=_FILE_TOOLS + _HANDOFF_TOOLS + ("web_search", "fetch_url"),
        accepts_from=("scout",),
        hands_to=("screenwriter", "producer"),
        extra_dirs=("docs/research", "docs/clients"),
        env_token="CREW_TOKEN_MARKETER",
    ),
    Role(
        key="screenwriter",
        title="Сценарист",
        tagline="Идеи роликов, сюжет, раскадровка. Работает от анализа, не выдумывает с нуля.",
        tools=_FILE_TOOLS + _HANDOFF_TOOLS + ("web_search",),
        accepts_from=("marketer",),
        hands_to=("prompt_engineer", "sound", "producer"),
        extra_dirs=("docs/creative",),
        env_token="CREW_TOKEN_SCREENWRITER",
    ),
    Role(
        key="prompt_engineer",
        title="Промпт-инженер",
        tagline="Character Bible, покадровые промты, генерация кадров.",
        tools=_FILE_TOOLS + _HANDOFF_TOOLS + ("image_generate",),
        accepts_from=("screenwriter",),
        hands_to=("producer",),
        extra_dirs=("docs/prompts", "docs/frames"),
        env_token="CREW_TOKEN_PROMPT_ENGINEER",
    ),
    Role(
        key="sound",
        title="Звукорежиссёр",
        tagline="Музыка, голос, звуковой пакет под ролик.",
        tools=_FILE_TOOLS + _HANDOFF_TOOLS + ("web_search",),
        accepts_from=("screenwriter",),
        hands_to=("producer",),
        extra_dirs=("docs/sound",),
        env_token="CREW_TOKEN_SOUND",
    ),
    Role(
        key="producer",
        title="Продюсер",
        tagline="Собирает финальный пакет, выбирает пайплайн, режет брак.",
        tools=_FILE_TOOLS + _HANDOFF_TOOLS + ("terminal",),
        accepts_from=("prompt_engineer", "sound", "marketer", "screenwriter"),
        hands_to=(),
        extra_dirs=("docs/final-production",),
        env_token="CREW_TOKEN_PRODUCER",
    ),
    Role(
        key="scout",
        title="Скаут",
        tagline="Ищет клиентов и проекты, отсекает мусор, приносит только пригодное.",
        tools=_FILE_TOOLS + ("web_search", "fetch_url", "submit_handoff"),
        accepts_from=(),
        hands_to=("marketer",),
        extra_dirs=("docs/leads",),
        env_token="CREW_TOKEN_SCOUT",
    ),
    Role(
        key="secretary",
        title="Секретарь",
        tagline="Держит состояние всех проектов, отвечает «что где стоит».",
        tools=_FILE_TOOLS + ("inbox_list", "read_handoff", "accept_handoff"),
        accepts_from=(),
        hands_to=(),
        extra_dirs=("docs/projects",),
        env_token="CREW_TOKEN_SECRETARY",
    ),
)


BY_KEY: dict[str, Role] = {r.key: r for r in ROLES}


def get_role(key: str) -> Role:
    role = BY_KEY.get((key or "").strip().lower())
    if role is None:
        known = ", ".join(sorted(BY_KEY))
        raise KeyError(f"Нет роли «{key}». Известные: {known}")
    return role


def workspace_of(role_key: str) -> Path:
    """Корень песочницы роли. Всё, что агент трогает, лежит только здесь."""
    return CREW_ROOT / get_role(role_key).key / "workspace"


def shared_dir() -> Path:
    """Общая папка: только очередь handoff. Ничего исполняемого."""
    return CREW_ROOT / "_shared"


def ensure_layout() -> None:
    """Создать папки всех ролей. Идемпотентно, безопасно звать при каждом старте."""
    shared_dir().mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        ws = workspace_of(role.key)
        for sub in ("docs", "docs/inbox/handoffs", "docs/inbox/done", "tmp", *role.extra_dirs):
            (ws / sub).mkdir(parents=True, exist_ok=True)
