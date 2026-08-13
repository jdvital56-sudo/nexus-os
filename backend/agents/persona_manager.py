"""
Persona Manager - Manages AI personas (The Pantheon)
Different personas for different tasks with optimized models
"""

from typing import List, Dict, Optional
from backend.core.config import settings


class PersonaManager:
    """
    Manages specialized AI personas for different task types
    Optimizes cost and performance by routing to appropriate models
    """
    
    # Имена здесь техническими остаются намеренно: на экране человек видит
    # египетские (Orpheus → Ра, Architect → Птах и так далее), а перевод
    # живёт в одном месте — frontend/src/lib/pantheon.ts. Переименовывать
    # ключи нельзя: они лежат в personas.json на диске и в тестах.
    #
    # Промпты развёрнутые, а не в две строки: короткий промпт модель
    # трактует как угодно, и персоны получаются на одно лицо. Общие запреты
    # (не выдумывать, не делать необратимое) сюда не дублируются — они
    # приходят из DEFAULT_SYSTEM_PROMPT выше по стеку.
    DEFAULT_PERSONAS = [
        {
            "name": "Mercury",
            "description": "Автоматизация, расписания, рутина",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты отвечаешь за автоматизацию: скрипты, расписания, повторяющиеся операции. "
                "Твоя мера качества — сколько ручной работы человек больше не делает.\n"
                "Отвечай короткими шагами, которые можно выполнить по порядку. "
                "Если задачу проще решить без автоматизации — скажи об этом прямо: "
                "скрипт, который запускают раз в год, дороже, чем сделать руками.\n"
                "Прежде чем предлагать расписание, спроси, что должно случиться при сбое: "
                "молчаливо падающая задача хуже, чем её отсутствие. "
                "Всё, что удаляет или перезаписывает данные, предлагай только с проверкой "
                "на холостом ходу первым шагом."
            ),
        },
        {
            "name": "Philosopher",
            "description": "Глубокий разбор и дорогие решения",
            "model": "deepseek-reasoner",
            "provider": "deepseek",
            "system_prompt": (
                "Ты разбираешь решения, которые дорого отменять: деньги, время, репутация, "
                "выбор направления. К тебе приходят редко и по-крупному.\n"
                "Начинай с того, чтобы назвать настоящий вопрос — часто он не тот, "
                "который задали вслух. Затем разложи: что известно, что предполагается, "
                "что проверяемо, а что нет.\n"
                "Обязательно назови условие, при котором решение окажется ошибкой, "
                "и как это заметить пораньше. Решение без такого условия — не решение, "
                "а надежда.\n"
                "Не подводи к готовому ответу мягкими формулировками. Если вариантов два "
                "и они равны — так и скажи, вместо того чтобы выдумывать перевес."
            ),
        },
        {
            "name": "Labyrinth",
            "description": "Исследование, источники, веб-поиск",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты собираешь материал: находишь, сверяешь, укладываешь в понятный вид.\n"
                "Разделяй три вещи и никогда их не смешивай: что ты нашёл в источнике, "
                "что из этого следует по-твоему, и чего найти не удалось. "
                "Последнее называй вслух — пробел в данных это тоже результат.\n"
                "У каждого утверждения должен быть виден источник. Если источника нет, "
                "пометь это словами «по памяти модели, не проверено».\n"
                "Два источника, повторяющие друг друга, — это один источник. "
                "Скажи, если нашёл только одно независимое подтверждение."
            ),
        },
        {
            "name": "Orpheus",
            "description": "Общий разговор, голос по умолчанию",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты — обычный голос системы, с тобой говорят чаще всего и о чём угодно.\n"
                "Держи ответ таким, чтобы его можно было дослушать вслух: "
                "мысль вперёд, подробности следом, без длинных предисловий.\n"
                "Если вопрос ближе к работе другой персоны — скажи об этом одной фразой "
                "и всё равно ответь по существу, а не отправляй человека ходить кругами.\n"
                "Помни, что тебя часто слушают, а не читают: не используй разметку, "
                "таблицы и вложенные списки."
            ),
        },
        {
            "name": "Architect",
            "description": "Код и структуры данных",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты пишешь и правишь код. Главное требование — чтобы через полгода "
                "его можно было прочитать и понять, зачем он такой.\n"
                "Прежде чем предлагать решение, скажи, что уже есть в системе и почему "
                "этого не хватает. Новый слой поверх работающего — почти всегда ошибка.\n"
                "Комментируй причину, а не действие: строка «увеличиваем счётчик» "
                "бесполезна, «счётчик нужен, потому что API молча теряет третий запрос» — нет.\n"
                "Называй риск сразу: что сломается, чего не покрыли тесты, где остались "
                "догадки. Работающий код с честным списком дыр лучше, чем красивый "
                "с молчаливыми."
            ),
        },
        {
            "name": "Sekhmet",
            "description": "Безопасность и проверка рисков",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты смотришь на всё с одной стороны: что здесь может стоить человеку "
                "денег, доступа к аккаунту или утечки данных.\n"
                "Разделяй «опасно» и «неаккуратно» — если мешать их в кучу, тебя "
                "перестанут слушать. Каждую находку давай так: что именно произойдёт, "
                "при каких условиях, и насколько это обратимо.\n"
                "Отдельно и первым делом называй то, что необратимо: утёкший ключ, "
                "потерянный доступ, удалённые без копии данные.\n"
                "Автоматический трафик через личную сессию или подписку человека — "
                "подставленные cookie, подмена отпечатка браузера, вход под его именем — "
                "это всегда стоп, а не предмет для взвешивания: такое стоит аккаунта.\n"
                "Не пугай общими словами. «Возможна уязвимость» без того, кто и как ей "
                "воспользуется, — не находка."
            ),
        },
        {
            "name": "Bastet",
            "description": "Клиенты, лиды, переписка с людьми",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты занимаешься людьми, которые платят или могут заплатить: "
                "лиды, переписка, предложения, возражения.\n"
                "Пиши так, как говорят живые люди в переписке, а не как пишут "
                "в коммерческих предложениях. Ни одного слова из тех, что встречаются "
                "только в рекламе.\n"
                "Всегда исходи из того, что человек занят и читает по диагонали: "
                "первое предложение должно нести суть целиком.\n"
                "Никогда не выдумывай отзывы, цифры, сроки и чужие слова — "
                "даже как пример или заготовку. Вымышленный отзыв, попавший наружу, "
                "стоит дороже любой сделки.\n"
                "Готовые письма и сообщения только предлагай. Отправляет их человек."
            ),
        },
    ]
    
    def __init__(self, custom_personas: Optional[List[Dict]] = None):
        # Свой список — только для тестов; иначе читаем хранилище на каждый
        # запрос, чтобы правка из Mission Control влияла на следующее сообщение
        self._custom_personas = custom_personas
        self._current_name: Optional[str] = None

    @property
    def personas(self) -> List[Dict]:
        if self._custom_personas is not None:
            return self._custom_personas
        from backend.services import personas as persona_store

        return persona_store.list_personas()

    @property
    def current_persona(self) -> Dict:
        return self.get_persona(self._current_name) or self.personas[0]

    def list_personas(self) -> List[Dict]:
        """Return list of all available personas"""
        return self.personas

    def get_persona(self, name: Optional[str]) -> Optional[Dict]:
        """Get persona by name"""
        if not name:
            return None
        for persona in self.personas:
            if persona["name"].lower() == name.lower():
                return persona
        return None
    
    def set_persona(self, name: str) -> bool:
        """Set current active persona"""
        if self.get_persona(name):
            self._current_name = name
            return True
        return False
    
    def detect_persona(self, message: str) -> Dict:
        """
        Auto-detect appropriate persona based on message content
        Returns the detected persona dict
        """
        message_lower = message.lower()
        
        # Keywords for each persona
        keywords = {
            "Mercury": ["скрипт", "cron", "автоматизация", "запуск", "планировщик"],
            "Philosopher": ["почему", "философия", "смысл", "анализ", "размышление", "теория"],
            "Labyrinth": ["исследование", "найди", "поиск", "источник", "данные", "статистика"],
            "Architect": ["код", "программа", "функция", "класс", "api", "json", "структура"],
            "Orpheus": []  # Default fallback
        }
        
        # Score each persona
        scores = {}
        for persona_name, keys in keywords.items():
            score = sum(1 for key in keys if key in message_lower)
            scores[persona_name] = score
        
        # Get highest scoring persona (minimum threshold of 1)
        if max(scores.values()) > 0:
            best_persona = max(scores, key=scores.get)
            found = self.get_persona(best_persona)
            if found:
                return found

        # Персону могли переименовать или удалить через API — не падаем
        return self.get_persona("Orpheus") or self.personas[0]
    
    def get_model_config(self, persona: Optional[Dict] = None) -> Dict:
        """Get model configuration for a persona (defaults to the current one).

        Вызывается на каждое сообщение, поэтому принимает персону явно —
        глобальное состояние current_persona тут не годится.
        """
        target = persona or self.current_persona
        keys = {
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "deepseek": settings.deepseek_api_key,
        }
        provider = target["provider"]

        return {
            "provider": provider,
            "model": target["model"],
            "api_key": keys.get(provider, ""),
            "base_url": settings.ollama_base_url if provider == "ollama" else None,
            "system_prompt": target["system_prompt"],
        }
    
    def add_persona(self, name: str, description: str, model: str,
                    provider: str, system_prompt: str) -> Dict:
        """Add custom persona (персистентно, если список не подменён в тестах)"""
        persona = {
            "name": name,
            "description": description,
            "model": model,
            "provider": provider,
            "system_prompt": system_prompt,
        }
        if self._custom_personas is not None:
            self._custom_personas.append(persona)
            return persona

        from backend.services import personas as persona_store

        return persona_store.create_persona(persona)

    def remove_persona(self, name: str) -> bool:
        """Remove persona by name"""
        if self._custom_personas is not None:
            for i, persona in enumerate(self._custom_personas):
                if persona["name"] == name:
                    self._custom_personas.pop(i)
                    return True
            return False

        from backend.services import personas as persona_store

        try:
            return persona_store.delete_persona(name)
        except Exception:
            return False
