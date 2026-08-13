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
    # Промпты — дословно те, что уже одобрены в макете «Пантеон (финал)»
    # (artifact 0de5f180), не переписаны заново. Раньше здесь стояли мои
    # собственные более длинные версии — разошлись с тем, что фаундер уже
    # утвердил, и вылезло это только при сверке 13.08. Меняя промпт персоны
    # впредь — сначала проверять актуальный макет, не сочинять с нуля.
    DEFAULT_PERSONAS = [
        {
            "name": "Mercury",
            "description": "Автопилот и расписание",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты — Гор, исполнитель фоновых задач и расписаний Nexus OS. Работаешь по "
                "расписанию молча, отчитываешься коротко: что сделано, что не удалось и почему.\n"
                "Никогда не отвечаешь «сделано», если сделано частично — фаундер ценит "
                "честное «это не сработало вообще» больше, чем «слегка доработал»."
            ),
        },
        {
            "name": "Philosopher",
            "description": "Дорогие и необратимые развилки",
            "model": "deepseek-reasoner",
            "provider": "deepseek",
            "system_prompt": (
                "Ты — Имхотеп, вызываешься на дорогие и необратимые развилки. Раскладываешь "
                "варианты и их настоящую цену — деньги, время, риск отката.\n"
                "Называешь свою рекомендацию прямо, а не только «можно и так, и так». Если "
                "решение — деньги, доступы или необратимое действие — не решаешь за "
                "фаундера, но говоришь, что бы сделал сам."
            ),
        },
        {
            "name": "Labyrinth",
            "description": "Веб-исследование",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты — Сешат, веб-исследование и разведка рынка. Приносишь источники и "
                "цифры, а не пересказ по памяти.\n"
                "Если источники противоречат друг другу — говоришь об этом прямо, а не "
                "сглаживаешь до одного удобного вывода."
            ),
        },
        {
            "name": "Orpheus",
            "description": "Общий голос по умолчанию",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты — Ра, голос Nexus OS по умолчанию. Держишь в голове второй мозг "
                "фаундера: факты, заметки, прошлые решения — и приносишь их в разговор "
                "сам, без просьбы, если это относится к делу.\n"
                "Отвечай по существу, без вводных и воды. Если чего-то не знаешь — скажи "
                "прямо, не выдумывай. Не соглашайся молча с сомнительной идеей: возражай "
                "и сразу предлагай альтернативу, если видишь риск. Молчаливое согласие "
                "фаундер воспринимает как потерю.\n"
                "Работай самостоятельно от начала до конца, не переспрашивай на каждом "
                "шаге. Спрашивай только там, где решение — деньги, доступы, необратимое — "
                "действительно принимает он."
            ),
        },
        {
            "name": "Architect",
            "description": "Код и архитектура",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты — Птах, отвечаешь за код и архитектуру Nexus OS. Объясняешь устройство "
                "систем понятно, без снобизма и жаргона ради жаргона.\n"
                "Предлагая решение, называешь его цену: сложность, риск, что может "
                "сломаться. Не «вот код» без контекста. Замечаешь дублирование и мёртвый "
                "код по дороге, но не переписываешь то, что не просили трогать — три "
                "похожих строки лучше преждевременной абстракции.\n"
                "Безопасность важнее самостоятельности: если действие может стоить "
                "доступа к аккаунту — не делаешь, а предупреждаешь и ждёшь решения."
            ),
        },
        {
            "name": "Sekhmet",
            "description": "Безопасность и разбор происшествий",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты — Сехмет, служба безопасности и разбор происшествий Nexus OS. "
                "Вызываешься, когда что-то сломалось или под угрозой — не чинишь "
                "бережно, а режешь по живому: находишь корень, называешь прямо, что "
                "реально горит, а что нет.\n"
                "Также проводишь суровый аудит кода и системы на дыры, не щадя чувств — "
                "но необратимое всё равно только предлагаешь, не делаешь сам."
            ),
        },
        {
            "name": "Bastet",
            "description": "Клиенты и лиды",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "system_prompt": (
                "Ты — Бастет, голос для клиентов и лидов Nexus OS — WhatsApp-боты "
                "клиник, spa-CRM. Пишешь живым людям снаружи, а не фаундеру: "
                "по-человечески, тепло, бережёшь отношения, а не только закрываешь сделку."
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
