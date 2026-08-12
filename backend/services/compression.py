"""Сжатие контекста перед отправкой в модель — обёртка над Headroom.

Экономия здесь не абстрактная: у системы дневной потолок расходов на LLM,
и всё, что не ушло в модель, остаётся в бюджете на полезную работу.

Три правила, которые делают это безопасным:
  выключено по умолчанию — включать флагом после проверки на живых прогонах;
  любая ошибка возвращает исходные сообщения нетронутыми — сжатие никогда
      не должно ронять диалог;
  короткие запросы не трогаем вообще — на них экономить нечего, а риск
      исказить смысл есть.

Headroom сам защищает от сжатия последнее сообщение пользователя: режет он
объёмные данные (логи, документы, выдачу инструментов), а не то, что человек
сказал. Это его же поведение, мы на него опираемся, но не полагаемся слепо —
см. тест про сохранность пользовательской реплики.
"""
import logging
import os

logger = logging.getLogger(__name__)

# Ниже этого порога сжимать бессмысленно: накладные расходы съедят выгоду,
# а риск потерять деталь останется.
MIN_TOKENS_TO_COMPRESS = 2000

ENABLED = os.getenv("NEXUS_COMPRESSION", "off").lower() in ("on", "true", "1")


def available() -> bool:
    """Установлен ли Headroom. Без него служба просто не вмешивается."""
    try:
        import headroom  # noqa: F401
    except Exception:
        return False
    return True


def compress_messages(
    messages: list[dict],
    model: str | None = None,
) -> tuple[list[dict], dict]:
    """Сжимает переписку перед отправкой. Возвращает (сообщения, отчёт).

    При выключенном флаге, отсутствии Headroom, коротком запросе или любой
    ошибке возвращает исходный список без изменений — вызывающему коду не
    нужно ничего знать про сжатие.
    """
    stats = {"applied": False, "tokens_before": 0, "tokens_after": 0, "saved": 0}

    if not ENABLED or not messages:
        return messages, stats

    try:
        import headroom
    except Exception:
        logger.debug("Headroom не установлен — сжатие пропущено")
        return messages, stats

    try:
        kwargs = {"model": model} if model else {}
        result = headroom.compress(messages, **kwargs)

        if result.tokens_before < MIN_TOKENS_TO_COMPRESS:
            return messages, stats

        stats = {
            "applied": True,
            "tokens_before": result.tokens_before,
            "tokens_after": result.tokens_after,
            "saved": result.tokens_saved,
            "transforms": list(result.transforms_applied),
        }
        logger.info(
            "Сжатие: %d → %d токенов (сэкономлено %d)",
            result.tokens_before, result.tokens_after, result.tokens_saved,
        )
        return list(result.messages), stats

    except Exception as e:
        # Сжатие — удобство, а не необходимость. Упасть из-за него нельзя.
        logger.warning("Сжатие не удалось, отправляю как есть: %s", e)
        return messages, stats


def estimate(messages: list[dict], model: str | None = None) -> dict:
    """Сколько бы сэкономили, ничего не отправляя. Для проверки до включения."""
    if not available() or not messages:
        return {"available": False}

    try:
        import headroom

        kwargs = {"model": model} if model else {}
        result = headroom.compress(messages, **kwargs)
        return {
            "available": True,
            "enabled": ENABLED,
            "tokens_before": result.tokens_before,
            "tokens_after": result.tokens_after,
            "saved": result.tokens_saved,
            "ratio": round(result.compression_ratio, 3),
            "transforms": list(result.transforms_applied),
        }
    except Exception as e:
        return {"available": True, "error": str(e)}
