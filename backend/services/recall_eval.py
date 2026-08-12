"""Измерение качества вспоминания.

До этого модуля мы улучшали recall вслепую: поменяли веса слоёв — стало
лучше или хуже, никто не знал. Здесь набор вопросов с заранее известными
правильными ответами и три метрики, которые ловят просадку.

Почему свой набор, а не Ragas: Ragas оценивает ответы через LLM — это
деньги за каждый прогон, недетерминированный результат и зависимость от
сети в тестах. Нам нужно проверять поиск, а не формулировки, и здесь
хватает точных метрик по идентификаторам фактов. Ragas имеет смысл позже,
когда будем оценивать сами ответы Гермеса.
"""
from dataclasses import dataclass, field

from . import memory as mem_svc
from .memory import MemoryLayer


@dataclass
class EvalCase:
    """Вопрос и факты, которые обязаны на него найтись."""

    question: str
    expected: list[str]  # содержимое фактов-ответов
    noise: list[str] = field(default_factory=list)  # похожие, но неправильные


# Набор намеренно бытовой: это те вопросы, ради которых система и строилась.
# Шум подобран так, чтобы совпадал по словам, но не по смыслу — именно на
# нём ломается наивный поиск по пересечению слов.
DEFAULT_CASES = [
    EvalCase(
        question="какая ставка у клиента по spa-офферу",
        expected=["Ставка по spa-офферу — 60 тысяч рублей в месяц"],
        noise=[
            "Ставка рефинансирования ЦБ выросла",
            "Клиент просил прислать оффер по почте",
        ],
    ),
    EvalCase(
        question="когда у нас созвон с подрядчиком",
        expected=["Созвон с подрядчиком назначен на четверг в 15:00"],
        noise=[
            "Подрядчик прислал смету",
            "Созвон с командой перенесли",
        ],
    ),
    EvalCase(
        question="какой моделью отвечает Гермес",
        expected=["Гермес отвечает через DeepSeek"],
        noise=[
            "Гермес — телеграм-бот проекта",
            "DeepSeek дешевле OpenAI",
        ],
    ),
    EvalCase(
        question="что решили по автопилоту",
        expected=["Автопилот Джарвиса выключен до недели работы гигиены памяти"],
        noise=[
            "Автопилот готов к запуску",
            "Джарвис оркестрирует агентов",
        ],
    ),
]


def seed(cases: list[EvalCase] | None = None) -> dict[str, list[str]]:
    """Заполняет память фактами набора. Возвращает вопрос → id правильных."""
    cases = cases or DEFAULT_CASES
    answer_ids: dict[str, list[str]] = {}

    for case in cases:
        ids = []
        for content in case.expected:
            fact = mem_svc.add_fact(
                content=content, layer=MemoryLayer.CANON, confidence=0.9
            )
            ids.append(fact.id)
        for content in case.noise:
            mem_svc.add_fact(content=content, layer=MemoryLayer.INBOX, confidence=0.5)
        answer_ids[case.question] = ids

    return answer_ids


def evaluate(cases: list[EvalCase] | None = None, limit: int = 5) -> dict:
    """Прогоняет набор и считает метрики.

    hit@1  — доля вопросов, где правильный факт оказался первым;
    hit@k  — доля, где он попал в выдачу вообще;
    MRR    — средняя обратная позиция: 1.0 если всегда первый, 0.5 если
             стабильно второй. Ловит просадку раньше, чем hit@k.
    """
    cases = cases or DEFAULT_CASES
    answer_ids = seed(cases)

    hits_1 = 0
    hits_k = 0
    reciprocal = 0.0
    misses = []

    for case in cases:
        expected = set(answer_ids[case.question])
        found = [f.id for f in mem_svc.recall(case.question, limit=limit)]

        position = next((i for i, fid in enumerate(found) if fid in expected), None)

        if position == 0:
            hits_1 += 1
        if position is not None:
            hits_k += 1
            reciprocal += 1 / (position + 1)
        else:
            misses.append(case.question)

    total = len(cases)
    return {
        "cases": total,
        "hit@1": round(hits_1 / total, 3),
        f"hit@{limit}": round(hits_k / total, 3),
        "mrr": round(reciprocal / total, 3),
        "misses": misses,
    }
