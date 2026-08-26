"""Резервная копия хранилища Obsidian на GitHub.

Единственное звено, которое переживёт смерть диска. Фаундер прямо
попросил полную автоотправку 26.08.2026, после того как выяснилось: его
82 заметки и вся память агента существовали в одном экземпляре на одном
компьютере, а последняя копия в облаке была от 11.08.

Репозиторий приватный, ветка `main`, `origin` уже настроен — плагин
obsidian-git его завёл, но автоотправку держал выключенной
(`autoPushInterval: 0`), поэтому коммиты копились локально и наружу не
уходили.

**Заслон от утечки.** Отправка автоматическая и без просмотра человеком,
поэтому перед каждой ищем ключи и токены. Нашли — не отправляем и громко
пишем в лог. Приватный репозиторий не оправдание: ключ в истории git
живёт вечно и утекает вместе с любым будущим доступом к репозиторию.
"""
import logging
import re
import subprocess

from ..core.config import settings

logger = logging.getLogger(__name__)

BRANCH = "main"
TIMEOUT = 120

# Формы настоящих секретов. Имена переменных (FAL_KEY, TELEGRAM_BOT_TOKEN)
# намеренно НЕ ловим: они в памяти упоминаются постоянно и без значений.
_SECRET = re.compile(
    r"""(
        sk-[A-Za-z0-9]{20,}                      # OpenAI/DeepSeek
      | AIza[0-9A-Za-z_\-]{30,}                  # Google
      | gh[pousr]_[A-Za-z0-9]{20,}               # GitHub
      | xox[baprs]-[A-Za-z0-9-]{20,}             # Slack
      | \b[0-9]{8,10}:AA[A-Za-z0-9_\-]{30,}\b    # Telegram bot token
      | \b[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}:[a-f0-9]{16,}\b  # fal.ai
    )""",
    re.VERBOSE,
)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", settings.obsidian_vault_path, *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def find_secrets(text: str) -> list[str]:
    """Возвращает вид найденных секретов — БЕЗ самих значений.

    Печатать секрет в лог, чтобы сообщить об утечке секрета, — это ещё
    одна утечка. Достаточно знать, что он есть.
    """
    return sorted({m.group(0)[:6] + "…" for m in _SECRET.finditer(text or "")})


def push() -> bool:
    """Коммитит изменения хранилища и отправляет на GitHub.

    Возвращает True, если что-то ушло. Нечего отправлять — тоже успех,
    молча.
    """
    vault = (settings.obsidian_vault_path or "").strip()
    if not vault:
        return False

    status = _git("status", "--porcelain")
    if status.returncode != 0:
        logger.warning("Хранилище не под git: %s", status.stderr.strip()[:200])
        return False
    if not status.stdout.strip():
        return False  # изменений нет — нормальный тихий случай

    # Проверяем именно то, что собираемся отправить
    _git("add", "-A")
    staged = _git("diff", "--cached")
    leaked = find_secrets(staged.stdout)
    if leaked:
        _git("reset")
        logger.error(
            "ОТПРАВКА ОТМЕНЕНА: в хранилище похоже на секреты (%s). "
            "Уберите их из заметок — иначе ключ уедет в историю git навсегда.",
            ", ".join(leaked),
        )
        return False

    commit = _git("commit", "-m", "Автокопия хранилища: заметки и память агента")
    if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
        logger.warning("Коммит хранилища не прошёл: %s", commit.stderr.strip()[:200])
        return False

    sent = _git("push", "origin", BRANCH)
    if sent.returncode != 0:
        logger.warning("Отправка на GitHub не прошла: %s", sent.stderr.strip()[:200])
        return False

    logger.info("Хранилище отправлено на GitHub")
    return True
