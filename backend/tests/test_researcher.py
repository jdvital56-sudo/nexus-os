"""Исследователь: ищет тренды по направлениям фаундера и предлагает темы.

Тот самый TREND AGENT из первой формулировки контент-завода (22.08.2026),
который так и не был построен: тема для сценариев приходила только голосом
от фаундера. Находки падают в раздел «Идеи» с пометкой «предложил Джарвис»
(source=system) — отдельного хранилища заводить не стали.

Направления настраиваются один раз и живут в файле: по кнопке и по
утреннему расписанию Исследователь ходит по ним сам, ничего не спрашивая —
в 9 утра спросить некого.
"""
import pytest

from backend.core.errors import ValidationError
from backend.services import ideas as ideas_svc
from backend.services import researcher


class StubLLM:
    """Возвращает готовый JSON с темами, как настоящая модель в json_mode."""

    def __init__(self, raw: str | None = None):
        self.raw = raw or (
            '[{"topic": "Утренние спа-ритуалы дома", "why": "растёт запрос на самоуход"},'
            ' {"topic": "Контрастный душ зимой", "why": "сезонный всплеск"}]'
        )
        self.prompts: list[str] = []

    async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
        self.prompts.append(user_message)
        return self.raw


class StubSearch:
    """Заглушка веб-поиска: настоящий Firecrawl стоит денег и ходит в сеть."""

    def __init__(self, results=None, fail=False):
        self.results = results if results is not None else [
            type("R", (), {"title": "Тренды велнеса 2026", "url": "https://x.test/1",
                           "snippet": "Самоуход дома набирает обороты"})(),
        ]
        self.fail = fail
        self.queries: list[str] = []

    async def __call__(self, query, limit=5):
        self.queries.append(query)
        if self.fail:
            from backend.services.websearch import SearchUnavailable

            raise SearchUnavailable("поиск не настроен")
        return self.results


# === Направления ===

def test_directions_empty_by_default():
    assert researcher.get_directions() == []


def test_set_and_get_directions():
    researcher.set_directions(["спа и велнес", "аренда жилья в Дубае"])
    assert researcher.get_directions() == ["спа и велнес", "аренда жилья в Дубае"]


def test_directions_are_trimmed_and_deduped():
    researcher.set_directions(["  спа  ", "спа", "", "оливки"])
    assert researcher.get_directions() == ["спа", "оливки"]


def test_directions_reject_garbage():
    with pytest.raises(ValidationError):
        researcher.set_directions(["", "   "])


# === Разведка по одному направлению ===

@pytest.mark.asyncio
async def test_research_creates_ideas(monkeypatch):
    search = StubSearch()
    monkeypatch.setattr(researcher.websearch, "search", search)

    created = await researcher.research("спа и велнес", llm=StubLLM())

    assert len(created) == 2
    assert created[0].source.value == "system"
    assert "спа" in search.queries[0].lower()

    stored = ideas_svc.list_ideas()
    assert len(stored) == 2
    # Контекст должен объяснять, откуда тема взялась: через неделю фаундер
    # не вспомнит, почему Джарвис это предложил.
    assert "спа и велнес" in stored[0].context


@pytest.mark.asyncio
async def test_research_requires_direction():
    with pytest.raises(ValidationError):
        await researcher.research("   ", llm=StubLLM())


@pytest.mark.asyncio
async def test_research_survives_dead_search(monkeypatch):
    """Firecrawl отвалился — честная ошибка, а не тихий пустой список."""
    monkeypatch.setattr(researcher.websearch, "search", StubSearch(fail=True))

    with pytest.raises(ValidationError):
        await researcher.research("спа", llm=StubLLM())


@pytest.mark.asyncio
async def test_research_ignores_garbage_from_model(monkeypatch):
    monkeypatch.setattr(researcher.websearch, "search", StubSearch())

    with pytest.raises(ValidationError):
        await researcher.research("спа", llm=StubLLM("это не json"))


@pytest.mark.asyncio
async def test_research_skips_duplicates(monkeypatch):
    """Утренний прогон не должен каждый день приносить одно и то же."""
    monkeypatch.setattr(researcher.websearch, "search", StubSearch())

    await researcher.research("спа", llm=StubLLM())
    second = await researcher.research("спа", llm=StubLLM())

    assert second == []
    assert len(ideas_svc.list_ideas()) == 2


@pytest.mark.asyncio
async def test_research_dedupe_ignores_case_and_spaces(monkeypatch):
    monkeypatch.setattr(researcher.websearch, "search", StubSearch())

    await researcher.research("спа", llm=StubLLM())
    same = '[{"topic": "  утренние СПА-ритуалы дома ", "why": "то же самое"}]'
    second = await researcher.research("спа", llm=StubLLM(same))

    assert second == []


# === Утренний обход всех направлений ===

@pytest.mark.asyncio
async def test_daily_sweep_walks_every_direction(monkeypatch):
    search = StubSearch()
    monkeypatch.setattr(researcher.websearch, "search", search)
    monkeypatch.setattr(researcher, "_llm", lambda: StubLLM())

    researcher.set_directions(["спа", "оливки"])
    count = await researcher.daily_sweep()

    assert count == 2  # по два предложения на направление, вычтены дубли
    assert len(search.queries) == 2


@pytest.mark.asyncio
async def test_daily_sweep_quiet_without_directions(monkeypatch):
    search = StubSearch()
    monkeypatch.setattr(researcher.websearch, "search", search)

    assert await researcher.daily_sweep() == 0
    assert search.queries == []


@pytest.mark.asyncio
async def test_daily_sweep_survives_one_broken_direction(monkeypatch):
    """Упавшее направление не должно рушить весь утренний обход."""
    calls = {"n": 0}

    async def flaky(query, limit=5):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("сеть отвалилась")
        return StubSearch().results

    monkeypatch.setattr(researcher.websearch, "search", flaky)
    monkeypatch.setattr(researcher, "_llm", lambda: StubLLM())

    researcher.set_directions(["первое", "второе"])
    count = await researcher.daily_sweep()

    assert count == 2  # второе направление отработало
    assert calls["n"] == 2
