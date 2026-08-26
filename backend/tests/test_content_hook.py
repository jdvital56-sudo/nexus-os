"""Автор хуков: первые три секунды, ради которых досматривают остальное.

Роль из инфографики фаундера («7 AI-сотрудников», прислана 23.08.2026) и
его прямое подтверждение 24.08: хук нужен. До этого сценарий писался одним
проходом, и начало получалось описательным — «сегодня поговорим о том,
как…», то есть ровно тем, на чём палец уходит дальше.

Хук просим в общем запросе плана (лишних денег не стоит), а переписать —
отдельным сфокусированным вызовом, где у модели одна задача.
"""
import pytest

from backend.core.errors import ValidationError
from backend.services import content_factory as svc


class PlanLLM:
    """Отвечает планом с хуком, как настоящая модель после правки промпта."""

    def __init__(self, raw: str | None = None):
        self.raw = raw or (
            '[{"hook": "Ты не ссоришься. Ты просто перестал рассказывать.",'
            ' "script": "Сценарий", "caption": "Подпись", "hashtags": ["а"]}]'
        )
        self.prompts: list[str] = []

    async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
        self.prompts.append(user_message)
        return self.raw


class HookLLM:
    def __init__(self, raw: str = '{"hook": "Новый хук"}'):
        self.raw = raw
        self.prompts: list[str] = []

    async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
        self.prompts.append(user_message)
        return self.raw


async def _draft(llm=None):
    items = await svc.generate_plan("отношения", count=1, llm=llm or PlanLLM())
    return items[0]


# === Хук приходит вместе с планом ===

@pytest.mark.asyncio
async def test_plan_asks_for_a_hook():
    llm = PlanLLM()
    await svc.generate_plan("отношения", count=1, llm=llm)
    assert "хук" in llm.prompts[0].lower()


@pytest.mark.asyncio
async def test_hook_is_stored():
    item = await _draft()
    assert item.hook == "Ты не ссоришься. Ты просто перестал рассказывать."


@pytest.mark.asyncio
async def test_plan_without_hook_still_works():
    """Старые черновики и упрямая модель не должны ронять создание плана."""
    llm = PlanLLM('[{"script": "С", "caption": "П", "hashtags": []}]')
    item = await _draft(llm)
    assert item.hook == ""
    assert item.script == "С"


# === Переписать хук отдельным проходом ===

@pytest.mark.asyncio
async def test_rewrite_hook_replaces_it():
    item = await _draft()
    updated = await svc.rewrite_hook(item.id, llm=HookLLM())
    assert updated.hook == "Новый хук"


@pytest.mark.asyncio
async def test_rewrite_hook_sees_the_script():
    """Хук без сценария — выдумка: он обязан обещать то, что дальше есть."""
    item = await _draft()
    llm = HookLLM()
    await svc.rewrite_hook(item.id, llm=llm)
    assert "Сценарий" in llm.prompts[0]


@pytest.mark.asyncio
async def test_rewrite_hook_avoids_repeating_the_old_one():
    """Просим не повторяться — иначе «перепиши» возвращает то же самое."""
    item = await _draft()
    llm = HookLLM()
    await svc.rewrite_hook(item.id, llm=llm)
    assert "Ты не ссоришься" in llm.prompts[0]


@pytest.mark.asyncio
async def test_rewrite_hook_falls_back_to_topic():
    """Сценарий пустой, но тема есть — работаем: тема тоже материал.

    Через generate_plan совсем пустой черновик не создать (тема
    обязательна), так что это единственный реальный вырожденный случай.
    """
    item = await _draft(PlanLLM('[{"script": "", "caption": "", "hashtags": []}]'))
    llm = HookLLM()
    await svc.rewrite_hook(item.id, llm=llm)
    assert "отношения" in llm.prompts[0]


@pytest.mark.asyncio
async def test_rewrite_hook_needs_material():
    """Черновик совсем без текста переписывать нечего — честная ошибка."""
    item = await _draft()
    raw = svc._load()
    for i in raw:
        if i["id"] == item.id:
            i["topic"] = i["script"] = i["caption"] = i["hook"] = ""
    svc._save(raw)

    with pytest.raises(ValidationError):
        await svc.rewrite_hook(item.id, llm=HookLLM())


@pytest.mark.asyncio
async def test_rewrite_hook_rejects_empty_answer():
    """Модель вернула пустое — оставляем старый хук, а не затираем его."""
    item = await _draft()
    with pytest.raises(ValidationError):
        await svc.rewrite_hook(item.id, llm=HookLLM('{"hook": "   "}'))

    assert svc.get_item(item.id).hook == "Ты не ссоришься. Ты просто перестал рассказывать."


@pytest.mark.asyncio
async def test_rewrite_hook_accepts_bare_string():
    """Модель часто отвечает просто строкой вместо объекта."""
    item = await _draft()
    updated = await svc.rewrite_hook(item.id, llm=HookLLM('"Просто строка"'))
    assert updated.hook == "Просто строка"


# === API ===

def test_api_rewrite_hook(client, monkeypatch):
    class FakeLLMService:
        def __init__(self, *args, **kwargs):
            pass

        async def generate_response(self, user_message, context="", kind="interactive", json_mode=False):
            if "хук" in user_message.lower() and "перепиши" in user_message.lower():
                return '{"hook": "Хук от API"}'
            return '[{"hook": "Первый", "script": "С", "caption": "П", "hashtags": []}]'

    import backend.services.llm as llm_mod
    monkeypatch.setattr(llm_mod, "LLMService", FakeLLMService)

    item_id = client.post("/api/content/plan", json={"topic": "тема", "count": 1}).json()[0]["id"]
    r = client.post(f"/api/content/{item_id}/hook")

    assert r.status_code == 200
    assert r.json()["hook"] == "Хук от API"
