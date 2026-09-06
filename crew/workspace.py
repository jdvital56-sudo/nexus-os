"""Песочница роли: всё, что агент читает и пишет, лежит внутри её папки.

Это единственная граница, которая реально держит. Белый список команд для
терминала обходится за минуту (`bash -c`, любой интерпретатор), фильтр
подозрительных строк — театр. А вот путь, который после `resolve()` не лежит
внутри `workspace`, отвергается независимо от того, что модель придумала:
`../`, абсолютный путь, симлинк наружу, UNC-путь, `~` — всё сводится к одной
проверке.

Отдельно: запись всегда атомарная. У этого проекта уже была гонка при записи
JSON — два писателя, один битый файл. Здесь та же болезнь лечится до того,
как проявится: пишем во временный файл рядом и переставляем `os.replace()`,
который на обеих ОС атомарен в пределах тома.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

from . import config

# Сколько раз повторить перестановку файла, если Windows её отбил. Восемь
# попыток с удвоением задержки — это ~0.5 секунды суммарно: дольше держать
# файл открытым не может ни один наш читатель.
REPLACE_ATTEMPTS = 8

# Больше этого агент не прочитает за раз: длинный файл вытесняет из контекста
# всё остальное, а модель всё равно не удержит. Обрезаем явно и говорим об этом.
MAX_READ_BYTES = 200_000

# Больше этого агент не запишет. Промпт-пакет на мегабайт — это не работа,
# а зациклившийся цикл.
MAX_WRITE_BYTES = 1_000_000

# Файлы, которые агент не увидит и не перезапишет никогда, даже внутри своей
# папки. Ключи не должны попадать в песочницу вовсе, но если попадут по
# ошибке человека — пусть не утекут в чат.
DENY_NAMES = {".env", ".env.local", "credentials.json", "gmail_token.json", ".git"}
DENY_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}


class WorkspaceError(RuntimeError):
    """Попытка выйти за границу песочницы или нарушить лимит."""


class Workspace:
    """Файловый доступ одной роли. Наружу не пускает."""

    def __init__(self, role_key: str) -> None:
        self.role = config.get_role(role_key)
        self.root = config.workspace_of(self.role.key)
        self.root.mkdir(parents=True, exist_ok=True)

    # --- границы ---------------------------------------------------------

    def resolve(self, relative: str) -> Path:
        """Привести путь агента к реальному и убедиться, что он внутри.

        Принимает и `docs/research/x.md`, и `/srv/hermes-marketer/workspace/
        docs/research/x.md` — второй вид модель выдаёт сама, насмотревшись на
        собственные прошлые ответы. Абсолютный путь, попавший внутрь нашей
        песочницы, законен; любой другой — нет.
        """
        raw = (relative or "").strip().replace("\\", "/")
        if not raw:
            raise WorkspaceError("Пустой путь.")

        candidate = Path(raw)
        if candidate.is_absolute() or raw.startswith("~"):
            expanded = Path(os.path.expanduser(raw))
            try:
                resolved = expanded.resolve()
            except OSError as exc:
                raise WorkspaceError(f"Не разобрал путь: {raw}") from exc
        else:
            resolved = (self.root / candidate).resolve()

        root = self.root.resolve()
        if resolved != root and root not in resolved.parents:
            raise WorkspaceError(
                f"Путь вне песочницы роли «{self.role.title}»: {raw}. "
                f"Доступна только папка {self._display(root)} и всё внутри неё."
            )

        for part in resolved.parts:
            if part in DENY_NAMES:
                raise WorkspaceError(f"Файл {part} закрыт для агента.")
        if resolved.suffix.lower() in DENY_SUFFIXES:
            raise WorkspaceError(f"Файлы {resolved.suffix} закрыты для агента.")

        return resolved

    def _display(self, path: Path) -> str:
        """Путь для показа модели: относительный, если внутри песочницы."""
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(path)

    # --- чтение ----------------------------------------------------------

    def read(self, relative: str) -> str:
        path = self.resolve(relative)
        if not path.exists():
            raise WorkspaceError(f"Нет файла {self._display(path)}.")
        if path.is_dir():
            raise WorkspaceError(f"{self._display(path)} — это папка, а не файл.")
        data = path.read_bytes()
        truncated = len(data) > MAX_READ_BYTES
        text = data[:MAX_READ_BYTES].decode("utf-8", errors="replace")
        if truncated:
            text += (
                f"\n\n[обрезано: файл {len(data)} байт, показаны первые "
                f"{MAX_READ_BYTES}]"
            )
        return text

    def list_dir(self, relative: str = ".") -> list[str]:
        path = self.resolve(relative)
        if not path.exists():
            raise WorkspaceError(f"Нет папки {self._display(path)}.")
        if not path.is_dir():
            raise WorkspaceError(f"{self._display(path)} — файл, а не папка.")
        out: list[str] = []
        for child in sorted(path.iterdir()):
            if child.name in DENY_NAMES:
                continue
            mark = "/" if child.is_dir() else ""
            size = "" if child.is_dir() else f"  {child.stat().st_size} б"
            out.append(f"{self._display(child)}{mark}{size}")
        return out

    def _check_glob(self, pattern: str) -> str:
        """Глоб — не путь, и `resolve()` к нему не применить.

        Найдено аудитом с рабочим эксплойтом: `*/../../../producer/workspace/
        docs/*` честно проходит через `Path.glob` и перечисляет файлы чужой
        роли. Прочитать их потом нельзя — `read_file` нормализует путь и
        отвергнет, — но имена файлов, структура чужих проектов и полный путь
        с именем пользователя уже утекли в модель. Поэтому `..` и абсолютный
        путь в шаблоне запрещены, а результат ещё раз фильтруется по факту.
        """
        pattern = (pattern or "").strip().replace("\\", "/")
        if not pattern:
            raise WorkspaceError("Пустой шаблон поиска.")
        parts = Path(pattern).parts
        if ".." in parts or Path(pattern).is_absolute() or pattern.startswith("~"):
            raise WorkspaceError(
                "В шаблоне поиска нельзя использовать `..` и абсолютные пути. "
                "Ищи внутри своей папки."
            )
        return pattern

    def _inside(self, path: Path) -> bool:
        """Правда ли путь лежит внутри песочницы — проверка по факту."""
        try:
            resolved = path.resolve()
        except OSError:
            return False
        root = self.root.resolve()
        return resolved == root or root in resolved.parents

    def _is_denied(self, path: Path) -> bool:
        """Закрытый файл — по имени, по расширению ИЛИ по имени папки.

        Проверка родительских папок обязательна: без неё `.git/config` с
        токеном в URL прекрасно находился поиском по содержимому, хотя
        `read_file` его не отдавал. Аудит это подтвердил запуском.
        """
        if path.suffix.lower() in DENY_SUFFIXES:
            return True
        try:
            parts = set(path.resolve().relative_to(self.root.resolve()).parts)
        except (ValueError, OSError):
            return True
        return bool(parts & DENY_NAMES)

    def search(self, pattern: str, limit: int = 50) -> list[str]:
        """Поиск по именам файлов. Глоб, а не регулярка: модель пишет глоб."""
        pattern = self._check_glob(pattern)
        if not pattern.startswith("**/"):
            pattern = f"**/{pattern}"
        found: list[str] = []
        for path in self.root.glob(pattern):
            if not self._inside(path) or self._is_denied(path):
                continue
            found.append(self._display(path) + ("/" if path.is_dir() else ""))
            if len(found) >= limit:
                break
        return sorted(found)

    def grep(self, needle: str, glob: str = "**/*.md", limit: int = 40) -> list[str]:
        """Поиск по содержимому. Нужен, чтобы агент нашёл handoff по slug."""
        needle_low = (needle or "").strip().lower()
        if not needle_low:
            raise WorkspaceError("Пустой запрос поиска.")
        glob = self._check_glob(glob)
        hits: list[str] = []
        for path in sorted(self.root.glob(glob)):
            if not path.is_file() or not self._inside(path) or self._is_denied(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if needle_low in line.lower():
                    hits.append(f"{self._display(path)}:{number}: {line.strip()[:200]}")
                    if len(hits) >= limit:
                        return hits
                    break
        return hits

    def list_files(self, relative: str = ".") -> list[str]:
        """Имена файлов в папке, без размеров и меток.

        Отдельно от `list_dir`, потому что вызывающему коду нужны имена, а не
        строки для показа: разбор строки обратно ломался на именах с двумя
        пробелами подряд.
        """
        path = self.resolve(relative)
        if not path.is_dir():
            raise WorkspaceError(f"{self._display(path)} — не папка.")
        return sorted(
            child.name
            for child in path.iterdir()
            if child.is_file() and not self._is_denied(child) and child.name not in DENY_NAMES
        )

    # --- запись ----------------------------------------------------------

    def write(self, relative: str, content: str) -> str:
        """Атомарная запись. Возвращает путь для показа человеку."""
        path = self.resolve(relative)
        payload = (content or "").encode("utf-8")
        if len(payload) > MAX_WRITE_BYTES:
            raise WorkspaceError(
                f"Файл {len(payload)} байт — больше лимита {MAX_WRITE_BYTES}. "
                "Раздели на части."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, payload)
        return self._display(path)

    def patch(self, relative: str, old: str, new: str) -> str:
        """Точечная замена. Строка обязана встречаться ровно один раз.

        Почему не «заменить все»: модель, промахнувшись мимо уникального
        фрагмента, тихо перепишет десять мест вместо одного, и это всплывёт
        через день. Пусть лучше упадёт сразу.
        """
        path = self.resolve(relative)
        if not path.exists():
            raise WorkspaceError(f"Нет файла {self._display(path)}.")
        text = path.read_text(encoding="utf-8", errors="replace")
        count = text.count(old)
        if count == 0:
            raise WorkspaceError(
                f"В {self._display(path)} нет такого фрагмента. "
                "Прочитай файл заново — он мог измениться."
            )
        if count > 1:
            raise WorkspaceError(
                f"Фрагмент встречается {count} раз в {self._display(path)}. "
                "Возьми кусок побольше, чтобы он стал единственным."
            )
        self._atomic_write(path, text.replace(old, new, 1).encode("utf-8"))
        return self._display(path)

    def append(self, relative: str, content: str) -> str:
        """Дописать в конец. Для журналов, где перезапись потеряла бы историю."""
        path = self.resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        joined = existing + ("" if existing.endswith("\n") or not existing else "\n") + content
        self._atomic_write(path, joined.encode("utf-8"))
        return self._display(path)

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        """Временный файл рядом + `os.replace`.

        Рядом, а не в системном temp: `os.replace` атомарен только в пределах
        одного тома, а temp может оказаться на другом диске — тогда вместо
        атомарной перестановки будет копирование, и гонка вернётся.

        Ретрай — не перестраховка, а лечение найденного. Тест на 15
        одновременных писателей и читателей падал с `PermissionError
        [WinError 5]`: на Windows перестановка отбивается, пока файл открыт
        кем-то ещё, даже на чтение. Сама перестановка при этом атомарна —
        читатель никогда не видит половину файла, — но вызов может не
        состояться, и без повтора запись просто терялась бы с ошибкой. На
        Linux этой ветки не бывает, там первый же `os.replace` проходит.
        """
        directory = path.parent
        directory.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(dir=str(directory), prefix=".tmp-", suffix=".part")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

            delay = 0.005
            for attempt in range(REPLACE_ATTEMPTS):
                try:
                    os.replace(temp_name, path)
                    return
                except PermissionError:
                    if attempt == REPLACE_ATTEMPTS - 1:
                        raise
                    time.sleep(delay)
                    delay = min(delay * 2, 0.2)
        except BaseException:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    # --- обслуживание ----------------------------------------------------

    def reset(self) -> None:
        """Снести песочницу. Только для тестов и ручной пересборки."""
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
