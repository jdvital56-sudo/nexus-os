"""Работа с хранилищем Obsidian из диалога: найти, прочитать, записать.

Синхронизация (obsidian_sync) втягивает заметки в граф — это разовый
импорт. Здесь другое: живой доступ к базе знаний прямо во время разговора,
чтобы Hermes отвечал, опираясь на то, что фаундер уже написал.

Запись никогда не затирает существующую заметку: новое дописывается в
конец с датой. Удалять заметки система не умеет вовсе (хартия §6, п.3).
"""
import logging
import re
from datetime import datetime
from pathlib import Path

from ..core.config import settings

logger = logging.getLogger(__name__)

# Куда складываем заметки, созданные из диалога
INBOX_FOLDER = "Nexus Inbox"

# Сколько заметок подмешиваем в контекст — длинный контекст размывает ответ
_SEARCH_LIMIT = 3

# Сколько символов заметки берём в контекст
_SNIPPET = 800

# Заголовок прямо заявляет, что внутри доступы — такую заметку не отдаём
# в модель целиком. Упоминание слова «токен» в проектной записи под это не
# подпадает: иначе половина базы знаний станет невидимой.
_SENSITIVE_TITLE = re.compile(
    r"(credential|password|пароли?|secret|секрет|private\s*key|приватный\s*ключ|"
    r"seed\s*phrase|доступы)",
    re.IGNORECASE,
)

# Строки вида «password: xxx» вырезаются из любой заметки — точечно,
# вместо того чтобы прятать весь текст.
_SECRET_LINE = re.compile(
    r"(?im)^.*\b(password|пароль|passwd|secret|секрет|api[_\- ]?key|apikey|"
    r"token|токен|client[_\- ]?secret|private[_\- ]?key|connection[_\- ]?string|"
    r"dsn|credentials?)\b\s*[:=].*$"
)

# Ключи известного вида: sk-..., ghp_..., AKIA..., длинные base64-хвосты
_SECRET_VALUE = re.compile(
    r"\b(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{12,}|"
    r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}|xox[baprs]-[A-Za-z0-9\-]{10,})"
)

_REDACTED = "[скрыто: доступы]"


def looks_sensitive(name: str, content: str = "") -> bool:
    """Заметка целиком про доступы — судим по заголовку, а не по упоминанию."""
    if _SENSITIVE_TITLE.search(name):
        return True
    # Тело считается опасным, только если секретов там много —
    # одна строка вырезается точечно и заметку не блокирует
    return len(_SECRET_LINE.findall(content[:4000])) >= 3


def redact(text: str) -> str:
    """Вырезает строки с доступами и ключи известного вида."""
    text = _SECRET_LINE.sub(_REDACTED, text)
    return _SECRET_VALUE.sub(_REDACTED, text)


class VaultNotConfigured(RuntimeError):
    """Путь к хранилищу Obsidian не задан или не существует."""


def vault_path() -> Path:
    """Путь к хранилищу. Бросает понятную ошибку, если его нет."""
    raw = (settings.obsidian_vault_path or "").strip()
    if not raw:
        raise VaultNotConfigured(
            "Хранилище Obsidian не подключено: задайте OBSIDIAN_VAULT_PATH в .env"
        )
    path = Path(raw)
    if not path.is_dir():
        raise VaultNotConfigured(f"Папка хранилища не найдена: {raw}")
    return path


def is_configured() -> bool:
    try:
        vault_path()
        return True
    except VaultNotConfigured:
        return False


def _safe_name(title: str) -> str:
    """Имя файла без символов, запрещённых в Windows и ломающих ссылки."""
    name = re.sub(r'[<>:"/\\|?*\[\]#^]', "", title).strip()
    name = re.sub(r"\s+", " ", name)
    return (name or "Без названия")[:120]


def search_notes(query: str, limit: int = _SEARCH_LIMIT) -> list[dict]:
    """Ищет заметки по словам запроса. Пустой запрос — пустой результат."""
    words = [w.lower() for w in re.findall(r"\w{3,}", query, flags=re.UNICODE)]
    if not words:
        return []

    root = vault_path()
    scored: list[tuple[float, dict]] = []

    for md in root.glob("**/*.md"):
        try:
            content = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        haystack = f"{md.stem}\n{content}".lower()
        hits = sum(1 for w in words if w in haystack)
        if not hits:
            continue

        # Совпадение в заголовке весит больше, чем где-то в теле
        title_hits = sum(1 for w in words if w in md.stem.lower())
        score = hits + title_hits * 2

        sensitive = looks_sensitive(md.stem, content)
        scored.append((score, {
            "title": md.stem,
            "path": str(md.relative_to(root)),
            "sensitive": sensitive,
            # Заметка про доступы не отдаётся вовсе; в остальных секретные
            # строки вырезаются, а полезный текст остаётся
            "excerpt": "" if sensitive else redact(content[:_SNIPPET]).strip(),
        }))

    scored.sort(key=lambda x: -x[0])
    return [note for _, note in scored[:limit]]


def read_note(name: str) -> dict:
    """Читает заметку по имени или относительному пути.

    Имя приходит снаружи (из карты графа, из диалога), поэтому путь
    обязательно проверяется: «../../.ssh/id_rsa» не должен читаться только
    потому, что кто-то так назвал узел.
    """
    root = vault_path().resolve()

    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise FileNotFoundError(f"Заметка '{name}' вне хранилища")
    if candidate.is_file():
        return {
            "title": candidate.stem,
            "path": str(candidate.relative_to(root)),
            "content": candidate.read_text(encoding="utf-8", errors="replace"),
        }

    target = _safe_name(name).lower()
    for md in root.glob("**/*.md"):
        if md.stem.lower() == target:
            return {
                "title": md.stem,
                "path": str(md.relative_to(root)),
                "content": md.read_text(encoding="utf-8", errors="replace"),
            }

    raise FileNotFoundError(f"Заметка '{name}' не найдена в хранилище")


def write_note(title: str, content: str, folder: str = INBOX_FOLDER) -> dict:
    """Создаёт заметку. Если такая уже есть — дописывает, а не затирает."""
    root = vault_path()
    target_dir = root / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    path = target_dir / f"{_safe_name(title)}.md"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if path.exists():
        existing = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(
            f"{existing.rstrip()}\n\n---\n\n_Дополнено {stamp} через Hermes_\n\n{content}\n",
            encoding="utf-8",
        )
        action = "appended"
    else:
        path.write_text(
            f"# {title}\n\n_Создано {stamp} через Hermes_\n\n{content}\n",
            encoding="utf-8",
        )
        action = "created"

    logger.info("Заметка %s: %s", action, path.name)
    return {
        "action": action,
        "title": title,
        "path": str(path.relative_to(root)),
    }


def context_for(query: str) -> str:
    """Кусок контекста для диалога из базы знаний. Пусто — если нечего дать."""
    if not is_configured():
        return ""
    try:
        notes = search_notes(query)
    except Exception:
        logger.debug("Поиск по хранилищу не удался", exc_info=True)
        return ""

    # Заметки с доступами в модель не отправляем ни при каких условиях
    safe = [n for n in notes if not n["sensitive"] and n["excerpt"]]
    if not safe:
        return ""
    blocks = "\n\n".join(f"[{n['title']}]\n{n['excerpt']}" for n in safe)
    return "Из твоей базы знаний Obsidian:\n" + blocks
