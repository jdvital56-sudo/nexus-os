"""Критик — второй проход только для Сехмет и Имхотепа (Philosopher).

Главное, что проверяется: остальные персоны его не видят вообще, сбой
критика не блокирует ответ, и PASS не трогает черновик.
"""
import pytest

from backend.services import critic
from backend.services.llm import LLMResponse


class FakeLLM:
    def __init__(self, replies: list[str]):
        # По одному ответу на каждый вызов chat(), по порядку
        self._replies = list(replies)
        self.calls: list[list] = []
        self.system_prompt = "персона"

    async def chat(self, messages, **kwargs):
        self.calls.append(messages)
        return LLMResponse(content=self._replies.pop(0), model="fake")


class BrokenLLM:
    async def chat(self, *args, **kwargs):
        raise RuntimeError("сеть недоступна")


def test_only_two_personas_get_a_critic():
    assert critic.needs_critic("Sekhmet") is True
    assert critic.needs_critic("Philosopher") is True
    assert critic.needs_critic("Orpheus") is False
    assert critic.needs_critic("Architect") is False
    assert critic.needs_critic("Bastet") is False


@pytest.mark.asyncio
async def test_pass_verdict_reports_no_revision_needed():
    llm = FakeLLM(["PASS. Ответ точный и по делу."])

    passed, verdict = await critic.review(llm, "Sekhmet", "вопрос", "черновик")

    assert passed is True
    assert "PASS" in verdict
    # Промпт критика параметризован именем персоны, не выдуман заново
    system_msg = llm.calls[0][0]
    assert system_msg.role == "system"
    assert "Sekhmet" in system_msg.content
    assert "Critic paired with" in system_msg.content


@pytest.mark.asyncio
async def test_needs_revision_verdict_is_reported():
    llm = FakeLLM(["NEEDS REVISION: утверждает цену без источника."])

    passed, verdict = await critic.review(llm, "Philosopher", "вопрос", "черновик")

    assert passed is False
    assert "NEEDS REVISION" in verdict


@pytest.mark.asyncio
async def test_critic_failure_does_not_block_the_reply():
    """Сеть легла или бюджет кончился — черновик уходит как есть, не падаем."""
    passed, verdict = await critic.review(BrokenLLM(), "Sekhmet", "вопрос", "черновик")

    assert passed is True
    assert verdict == ""


@pytest.mark.asyncio
async def test_revise_asks_the_persona_to_fix_the_specific_problem():
    llm = FakeLLM(["поправленный ответ"])

    fixed = await critic.revise(llm, "системный промпт персоны", "вопрос", "черновик", "нашёл проблему X")

    assert fixed == "поправленный ответ"
    sent = llm.calls[0]
    assert sent[0].role == "system" and sent[0].content == "системный промпт персоны"
    assert sent[1].content == "вопрос"
    assert sent[2].content == "черновик"
    assert "проблему X" in sent[3].content


@pytest.mark.asyncio
async def test_revise_failure_falls_back_to_the_draft():
    fixed = await critic.revise(BrokenLLM(), "промпт", "вопрос", "черновик", "проблема")

    assert fixed == "черновик"


# --- Советчик: только Птах (Architect) пока, см. critic.py ---


def test_only_architect_gets_an_advisor():
    assert critic.needs_advisor("Architect") is True
    assert critic.needs_advisor("Orpheus") is False
    assert critic.needs_advisor("Sekhmet") is False


@pytest.mark.asyncio
async def test_real_suggestion_is_returned():
    llm = FakeLLM(["Дешевле использовать существующий кэш вместо нового запроса."])

    suggestion = await critic.advise(llm, "Architect", "вопрос", "черновик")

    assert suggestion == "Дешевле использовать существующий кэш вместо нового запроса."
    system_msg = llm.calls[0][0]
    assert "Architect" in system_msg.content
    assert "Advisor paired with" in system_msg.content


@pytest.mark.asyncio
async def test_no_addition_becomes_none():
    """«Добавить нечего» не должно пристёгиваться к ответу как совет."""
    llm = FakeLLM(["no addition"])

    suggestion = await critic.advise(llm, "Architect", "вопрос", "черновик")

    assert suggestion is None


@pytest.mark.asyncio
async def test_advisor_failure_returns_none_not_an_error():
    suggestion = await critic.advise(BrokenLLM(), "Architect", "вопрос", "черновик")

    assert suggestion is None
