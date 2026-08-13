"""Критик и советчик — второй проход поверх черновика ответа, точечно.

Согласовано с фаундером 13.08.2026: полное раскрытие (критик+советчик у
каждой персоны) — 3x вызовов модели на каждую задачу, дорого масштабировать
на все сразу. Критик подключён к Сехмет (проверяет свои же находки по
безопасности) и Имхотепу (technical name Philosopher — дорогие и
необратимые развилки, вызывается редко). Советчик подключён 14.08.2026 к
Птаху (technical name Architect) — код и архитектура, «быстрее/дешевле
сделать то же самое» здесь конкретно и часто по делу; по расценкам
DeepSeek (`budget.py`) один проход — около $0.0003, на дневной бюджет не
влияет. Критик правит черновик сам; советчик только пристёгивает одну
строку — Птах не обязан соглашаться, решение всё равно у фаундера.

Шаблоны — дословно то, что уже было согласовано с фаундером, не сочинены
заново (сессия 13.08.2026, «Nexus OS продолжение»).
"""
import logging

from . import budget
from .llm import LLMMessage, LLMService

logger = logging.getLogger(__name__)

# Технические имена персон (persona_manager.py), не отображаемые
PERSONAS_WITH_CRITIC = {"Sekhmet", "Philosopher"}
PERSONAS_WITH_ADVISOR = {"Architect"}

CRITIC_TEMPLATE = """You are the Critic paired with {persona}. You do not generate the primary answer — you review it before it reaches the founder.

Check for: factual claims stated without a real source or clear reasoning behind them; overconfidence where the honest answer is "I don't know" or "I'm not sure"; silent agreement with a flawed idea instead of pushing back; anything irreversible (deletions, sends, payments, publishing) proposed as if already decided rather than flagged for explicit approval; scope creep — solving more than what was actually asked.

Output format: a short verdict (PASS / NEEDS REVISION) plus, if NEEDS REVISION, the specific line and the specific problem — not a rewrite, not a lecture. The original agent fixes it, you don't do their job for them.

If the answer is genuinely fine, say so in one line and stop. A critic that always finds something to nitpick is worse than useless — it burns the founder's time and money for no signal."""

ADVISOR_TEMPLATE = """You are the Advisor paired with {persona}. You look at the same task before the primary answer is finalized, and suggest ONE improvement if there is a real one — not a list, not a rewrite.

Only speak up if: there's a faster or cheaper way to get the same result; a past decision or fact in memory is directly relevant and was missed; the approach works but a slightly different framing would land much better with how the founder actually thinks and works.

If you have nothing genuinely useful to add, say "no addition" and stop — do not manufacture a suggestion to justify being called. A советник who always has an opinion stops being trusted.

Never suggest anything that touches money, access, or irreversible actions — that decision path goes through the founder directly, not through you."""


def needs_critic(persona_name: str) -> bool:
    return persona_name in PERSONAS_WITH_CRITIC


def needs_advisor(persona_name: str) -> bool:
    return persona_name in PERSONAS_WITH_ADVISOR


async def review(llm: LLMService, persona_name: str, question: str, draft: str) -> tuple[bool, str]:
    """Просит критика оценить черновик. (True, "") — PASS, без правок.

    Сбой критика (сеть, бюджет) не должен блокировать ответ фаундеру —
    в этом случае черновик уходит как есть, будто критик сказал PASS.
    """
    system = CRITIC_TEMPLATE.format(persona=persona_name)
    user = f"Question: {question}\n\nDraft reply: {draft}"
    try:
        response = await llm.chat(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=user),
            ],
            temperature=0.2,
            max_tokens=300,
            kind=budget.INTERACTIVE,
        )
    except Exception:
        logger.exception("Критик %s не смог проверить ответ — пропускаем без правки", persona_name)
        return True, ""

    verdict = response.content.strip()
    passed = verdict.upper().startswith("PASS")
    return passed, verdict


async def revise(
    llm: LLMService,
    persona_system_prompt: str,
    question: str,
    draft: str,
    critique: str,
) -> str:
    """Просит саму персону поправить черновик по конкретному замечанию критика.

    Не пересобирает контекст/инструменты заново — критик находит проблему
    уровня текста (недосказанность, самоуверенность, скрытая необратимость),
    не фактическую ошибку, требующую нового поиска."""
    try:
        response = await llm.chat(
            [
                LLMMessage(role="system", content=persona_system_prompt),
                LLMMessage(role="user", content=question),
                LLMMessage(role="assistant", content=draft),
                LLMMessage(
                    role="user",
                    content=(
                        f"Критик проверил твой черновик и нашёл проблему: {critique}\n\n"
                        "Поправь ответ с учётом этого. Не переписывай заново то, что уже верно."
                    ),
                ),
            ],
            temperature=0.7,
            kind=budget.INTERACTIVE,
        )
    except Exception:
        logger.exception("Правка по критике не удалась — уходит черновик")
        return draft
    return response.content


async def advise(llm: LLMService, persona_name: str, question: str, draft: str) -> str | None:
    """Просит советчика посмотреть на черновик. None — добавить нечего.

    В отличие от критика ничего не правит — только предлагает одну строку,
    решение принимает не он. Сбой (сеть, бюджет) — то же самое, что "нечего
    добавить": ответ уходит без совета, не падает."""
    system = ADVISOR_TEMPLATE.format(persona=persona_name)
    user = f"Question: {question}\n\nDraft reply: {draft}"
    try:
        response = await llm.chat(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=user),
            ],
            temperature=0.3,
            max_tokens=200,
            kind=budget.INTERACTIVE,
        )
    except Exception:
        logger.exception("Советчик %s не смог посмотреть черновик — пропускаем", persona_name)
        return None

    suggestion = response.content.strip()
    if not suggestion or suggestion.lower().startswith("no addition"):
        return None
    return suggestion
