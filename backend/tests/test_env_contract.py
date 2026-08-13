"""Договор между .env и кодом.

2026-08-12 фаундер прислал скрин: голосовые не расшифровываются. Ключ Gemini
у него был вписан в .env под именем GEMINI_API_KEY — ровно как в примере, —
а код читал NEXSYS_GEMINI_API_KEY. Ключ лежал на месте и молча не работал.

Починить один ключ мало: причина в том, что имена в примере и в коде живут
независимо и расходятся незаметно. Этот тест их связывает: любая строка из
.env.example обязана где-то читаться. Если кто-то добавит настройку в
пример и забудет прочитать её в коде — упадёт здесь, а не через месяц в
Телеграме.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"

# Читается не через os.getenv, а особым путём — перечислено явно, чтобы
# список исключений был виден, а не растворялся в проверке
KNOWN_INDIRECT: set[str] = set()


def _names_from_example() -> list[str]:
    names = []
    for line in EXAMPLE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.append(line.split("=", 1)[0].strip())
    return names


def _code() -> str:
    text = []
    for folder in ("backend", "hermes", "cli"):
        for path in (ROOT / folder).rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            text.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(text)


@pytest.mark.skipif(not EXAMPLE.exists(), reason="нет .env.example")
def test_every_documented_key_is_read_by_the_code():
    code = _code()
    orphans = [
        name
        for name in _names_from_example()
        if name not in KNOWN_INDIRECT and not re.search(rf'["\']{re.escape(name)}["\']', code)
    ]

    assert not orphans, (
        "Эти настройки описаны в .env.example, но код их нигде не читает — "
        f"человек впишет значение, и оно молча не сработает: {orphans}"
    )


@pytest.mark.skipif(not EXAMPLE.exists(), reason="нет .env.example")
def test_example_has_no_secrets():
    """В примере должны быть пустые значения: файл лежит в репозитории."""
    filled = []
    for line in EXAMPLE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        # Значения по умолчанию — это не секреты: у ключей и токенов пусто.
        # Число секретом быть не может: MAX_REPLY_TOKENS — это лимит, а не ключ
        looks_secret = any(word in name.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
        if value and looks_secret and not value.isdigit():
            filled.append(name.strip())

    assert not filled, f"В .env.example лежат заполненные секреты: {filled}"


def test_gemini_key_is_read_under_both_names():
    """Тот самый ключ: короткое имя из .env и старое с приставкой."""
    code = _code()

    assert '"GEMINI_API_KEY"' in code
    assert '"NEXSYS_GEMINI_API_KEY"' in code
