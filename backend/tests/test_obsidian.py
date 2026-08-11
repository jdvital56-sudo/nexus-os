"""Тесты живой работы с базой знаний Obsidian (PR-13)."""
import pytest

from backend.core.config import settings
from backend.services import obsidian


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Маленькое хранилище с парой заметок."""
    root = tmp_path / "vault"
    (root / "Проекты").mkdir(parents=True)
    (root / "Проекты" / "Nexus OS.md").write_text(
        "# Nexus OS\n\nЛичная операционная система. Бот Hermes, персона Orpheus.\n#проект",
        encoding="utf-8",
    )
    (root / "Клиенты.md").write_text(
        "Спа-салон платит 500 долларов в месяц за сайт и CRM.",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "obsidian_vault_path", str(root))
    return root


def test_missing_vault_says_what_to_do(monkeypatch):
    monkeypatch.setattr(settings, "obsidian_vault_path", "")

    with pytest.raises(obsidian.VaultNotConfigured) as e:
        obsidian.vault_path()

    assert "OBSIDIAN_VAULT_PATH" in str(e.value)


def test_wrong_path_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "obsidian_vault_path", "C:/нет/такой/папки")

    assert obsidian.is_configured() is False


def test_search_finds_by_content(vault):
    found = obsidian.search_notes("спа салон")

    assert [n["title"] for n in found] == ["Клиенты"]


def test_search_prefers_title_matches(vault):
    found = obsidian.search_notes("Nexus")

    assert found[0]["title"] == "Nexus OS"


def test_search_ignores_short_words(vault):
    assert obsidian.search_notes("и в на") == []


def test_search_without_matches_is_empty(vault):
    assert obsidian.search_notes("криптовалюта майнинг") == []


def test_read_note_by_name(vault):
    note = obsidian.read_note("Клиенты")

    assert "500 долларов" in note["content"]


def test_read_missing_note_raises(vault):
    with pytest.raises(FileNotFoundError):
        obsidian.read_note("Такой заметки нет")


def test_write_creates_note(vault):
    result = obsidian.write_note("Идея приложения", "Ассистент из кармана.")

    assert result["action"] == "created"
    path = vault / obsidian.INBOX_FOLDER / "Идея приложения.md"
    assert "Ассистент из кармана" in path.read_text(encoding="utf-8")


def test_write_never_overwrites(vault):
    """Существующая заметка дополняется, а не затирается."""
    obsidian.write_note("Дневник", "Первая запись.")
    result = obsidian.write_note("Дневник", "Вторая запись.")

    content = (vault / obsidian.INBOX_FOLDER / "Дневник.md").read_text(encoding="utf-8")
    assert result["action"] == "appended"
    assert "Первая запись" in content
    assert "Вторая запись" in content


def test_unsafe_title_is_sanitised(vault):
    result = obsidian.write_note('Отчёт: "Q1/Q2" <черновик>', "текст")

    assert ":" not in result["path"].split("/")[-1]
    assert (vault / result["path"]).is_file()


def test_context_is_empty_without_vault(monkeypatch):
    monkeypatch.setattr(settings, "obsidian_vault_path", "")
    assert obsidian.context_for("что угодно") == ""


def test_context_carries_notes(vault):
    context = obsidian.context_for("Nexus OS")

    assert "obsidian" in context.lower()
    assert "Hermes" in context


# --- Команды из диалога ---


class Stub:
    async def generate_response(self, m, context="", kind="interactive", json_mode=False):
        self.last_context = context
        return "ответ модели"


def make_service(llm=None):
    from backend.services.conversation import ConversationService

    return ConversationService(
        llm=llm or Stub(), semantic_dedup=False, extract_entities=False
    )


@pytest.mark.asyncio
async def test_note_command_writes_to_vault(vault):
    svc = make_service()

    reply = await svc.handle("telegram", "42", "/note Идея | Ассистент в кармане")
    await svc.drain()

    assert "создана" in reply
    assert (vault / obsidian.INBOX_FOLDER / "Идея.md").is_file()


@pytest.mark.asyncio
async def test_russian_note_command_works(vault):
    svc = make_service()

    reply = await svc.handle("telegram", "42", "заметка Встреча | Обсудили сроки")

    assert "создана" in reply


@pytest.mark.asyncio
async def test_note_without_body_explains_format(vault):
    svc = make_service()

    reply = await svc.handle("telegram", "42", "/note Заголовок |   ")

    assert "Нужен текст" in reply


@pytest.mark.asyncio
async def test_notes_search_command(vault):
    svc = make_service()

    reply = await svc.handle("telegram", "42", "/notes спа салон")

    assert "Клиенты" in reply


@pytest.mark.asyncio
async def test_search_without_vault_says_so(monkeypatch):
    monkeypatch.setattr(settings, "obsidian_vault_path", "")
    svc = make_service()

    reply = await svc.handle("telegram", "42", "/notes что-нибудь")

    assert "OBSIDIAN_VAULT_PATH" in reply


@pytest.mark.asyncio
async def test_vault_reaches_the_model(vault):
    """DoD PR-13: база знаний участвует в обычном диалоге."""
    llm = Stub()
    svc = make_service(llm)

    await svc.handle("telegram", "42", "расскажи про Nexus OS")
    await svc.drain()

    assert "Hermes" in llm.last_context


@pytest.mark.asyncio
async def test_ordinary_message_is_not_a_note_command(vault):
    llm = Stub()
    svc = make_service(llm)

    reply = await svc.handle("telegram", "42", "сделай заметку о том, что я думаю")

    assert reply == "ответ модели"


# --- Заметки с доступами не уходят в модель ---


@pytest.fixture
def vault_with_secrets(vault):
    (vault / "Project serenity-crm — DB credentials.md").write_text(
        "host: db.example.com\nuser: admin\npassword: SuperSecret123",
        encoding="utf-8",
    )
    return vault


def test_note_about_credentials_is_blocked_whole():
    assert obsidian.looks_sensitive("Project — DB credentials")


def test_project_note_mentioning_token_is_not_blocked():
    """Иначе половина базы знаний станет невидимой из-за одного слова."""
    assert not obsidian.looks_sensitive(
        "2026-07-15 - Nexus Telegram-ассистент",
        "Настроили бота, положили token в .env, обсудили Guardian.",
    )


def test_note_stuffed_with_secrets_is_blocked():
    body = "password: a\napi_key: b\ntoken: c\n"
    assert obsidian.looks_sensitive("Просто заметка", body)


def test_secret_lines_are_cut_out():
    text = "Обсудили сроки\npassword: SuperSecret123\nДоговорились о цене"

    result = obsidian.redact(text)

    assert "SuperSecret123" not in result
    assert "Обсудили сроки" in result
    assert "Договорились о цене" in result


def test_known_key_formats_are_cut_out():
    assert "sk-" not in obsidian.redact("ключ sk-abcdefghijklmnopqrstuvwxyz123456")


def test_secrets_never_reach_the_model(vault_with_secrets):
    """Запрос к LLM — отправка данных наружу; доступы туда не идут."""
    context = obsidian.context_for("serenity crm credentials database")

    assert "SuperSecret123" not in context
    assert "password" not in context.lower()


def test_search_hides_body_of_sensitive_note(vault_with_secrets):
    found = obsidian.search_notes("credentials")

    secret = [n for n in found if "credentials" in n["title"].lower()][0]
    assert secret["sensitive"] is True
    assert secret["excerpt"] == ""


@pytest.mark.asyncio
async def test_search_command_still_finds_secret_note_by_title(vault_with_secrets):
    """Найти заметку можно — увидеть её содержимое через бота нельзя."""
    svc = make_service()

    reply = await svc.handle("telegram", "42", "/notes credentials")

    assert "credentials" in reply.lower()
    assert "SuperSecret123" not in reply
