"""Качество вспоминания — измеряемое, а не на глаз.

Эти тесты падают, если recall станет хуже. Без них любая правка весов или
поиска — ставка вслепую: цифры до неё никто не снимал.
"""
import pytest

from backend.services import memory as mem_svc
from backend.services import recall_eval
from backend.services.memory import MemoryLayer


@pytest.fixture(autouse=True)
def no_vector_search(monkeypatch):
    """Меряем текстовый поиск.

    Векторный требует ChromaDB и даёт разные ответы от прогона к прогону —
    порог по нему был бы плавающим и бесполезным.
    """
    monkeypatch.setattr(mem_svc, "INDEXING_ENABLED", False)


# === Пороги ===


def test_recall_finds_the_right_fact_first():
    report = recall_eval.evaluate()
    assert report["hit@1"] >= 0.9, f"правильный ответ перестал быть первым: {report}"


def test_recall_never_loses_the_answer_entirely():
    report = recall_eval.evaluate()
    assert report["misses"] == [], f"ответ не найден вовсе: {report['misses']}"


def test_mean_reciprocal_rank_holds():
    """MRR ловит просадку раньше, чем hit@k: ответ ещё находится, но ниже."""
    report = recall_eval.evaluate()
    assert report["mrr"] >= 0.9, f"ответы поехали вниз по выдаче: {report}"


# === Защита от двух найденных багов ===


def test_russian_word_forms_match():
    """«автопилоту» обязан находить «Автопилот».

    До обрезки до основы этот вопрос не находил ответ вообще — сравнение
    шло по словоформам целиком.
    """
    fact = mem_svc.add_fact(
        content="Автопилот Джарвиса выключен до недели работы гигиены памяти",
        layer=MemoryLayer.CANON,
        confidence=0.9,
    )
    found = [f.id for f in mem_svc.recall("что решили по автопилоту")]
    assert fact.id in found


@pytest.mark.parametrize("question,expected_word", [
    ("какая ставка у клиента", "Ставка"),
    ("когда созвон с подрядчиком", "Созвон"),
    ("какой моделью отвечает Гермес", "Гермес"),
])
def test_common_question_forms(question, expected_word):
    fact = mem_svc.add_fact(
        content=f"{expected_word} — важная деталь по проекту",
        layer=MemoryLayer.CANON,
        confidence=0.9,
    )
    assert fact.id in [f.id for f in mem_svc.recall(question)]


def test_stop_words_do_not_win():
    """Предлог «по» совпадает в любых двух фразах и не должен решать исход.

    Из-за него вопрос про автопилот выдавал первым факт про ставку.
    """
    right = mem_svc.add_fact(
        content="Автопилот Джарвиса выключен",
        layer=MemoryLayer.CANON, confidence=0.9,
    )
    mem_svc.add_fact(
        content="Ставка по spa-офферу — 60 тысяч рублей в месяц",
        layer=MemoryLayer.CANON, confidence=0.9,
    )
    assert mem_svc.recall("что решили по автопилоту")[0].id == right.id


def test_stems_drop_stop_words():
    assert mem_svc._stems("что решили по автопилоту") == {"решил", "автоп"}


def test_stem_is_stable_across_forms():
    assert mem_svc._stem("автопилот") == mem_svc._stem("автопилоту")
    assert mem_svc._stem("ставка") == mem_svc._stem("ставке")


# === Сам инструмент измерения ===


def test_seed_creates_expected_and_noise():
    ids = recall_eval.seed()
    assert len(ids) == len(recall_eval.DEFAULT_CASES)
    assert all(len(v) >= 1 for v in ids.values())
    assert len(mem_svc.get_facts(limit=100)) > len(recall_eval.DEFAULT_CASES)


def test_evaluate_reports_all_metrics():
    report = recall_eval.evaluate()
    assert set(report) >= {"cases", "hit@1", "hit@5", "mrr", "misses"}
    assert report["cases"] == len(recall_eval.DEFAULT_CASES)


def test_evaluate_on_custom_cases():
    case = recall_eval.EvalCase(
        question="сколько стоит подписка",
        expected=["Подписка стоит 20 долларов в месяц"],
        noise=["Подписка на рассылку оформлена"],
    )
    report = recall_eval.evaluate([case])
    assert report["cases"] == 1
    assert report["hit@1"] == 1.0
