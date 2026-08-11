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
    
    DEFAULT_PERSONAS = [
        {
            "name": "Mercury",
            "description": "Автономные скрипты и Cron-задачи",
            "model": "llama-3.3-70b",  # Free/Cheap model
            "provider": "ollama",
            "system_prompt": "Ты Mercury, эффективный исполнитель для автоматизации. Отвечай кратко, по делу. Фокус на скриптах, cron-задачах и рутинных операциях."
        },
        {
            "name": "Philosopher",
            "description": "Глубокие философские рассуждения и системный анализ",
            "model": "claude-3-opus-20240229",  # High-quality model
            "provider": "anthropic",
            "system_prompt": "Ты Philosopher, глубокий мыслитель. Анализируй сложные вопросы, рассматривай multiple perspectives, давай развернутые ответы с нюансами."
        },
        {
            "name": "Labyrinth",
            "description": "Исследовательские циклы и веб-поиск",
            "model": "gpt-4-turbo",  # Good for research
            "provider": "openai",
            "system_prompt": "Ты Labyrinth, исследователь. Ищи информацию, анализируй источники, предоставляй структурированные данные с цитатами."
        },
        {
            "name": "Orpheus",
            "description": "Общая аналитика и произвольные темы",
            "model": "deepseek-chat",  # Cost-effective generalist
            "provider": "deepseek",
            "system_prompt": "Ты Orpheus, универсальный аналитик. Помогай с любыми вопросами, от технических до творческих. Будь дружелюбным и полезным."
        },
        {
            "name": "Architect",
            "description": "Написание кода и структурирование данных",
            "model": "claude-3.5-sonnet",  # Excellent for code
            "provider": "anthropic",
            "system_prompt": "Ты Architect, эксперт по коду. Пиши чистый, поддерживаемый код. Объясняй решения, предлагай лучшие практики."
        }
    ]
    
    def __init__(self, custom_personas: Optional[List[Dict]] = None):
        self.personas = custom_personas or self.DEFAULT_PERSONAS.copy()
        self.current_persona = self.personas[0]  # Default to Mercury
    
    def list_personas(self) -> List[Dict]:
        """Return list of all available personas"""
        return self.personas
    
    def get_persona(self, name: str) -> Optional[Dict]:
        """Get persona by name"""
        for persona in self.personas:
            if persona["name"].lower() == name.lower():
                return persona
        return None
    
    def set_persona(self, name: str) -> bool:
        """Set current active persona"""
        persona = self.get_persona(name)
        if persona:
            self.current_persona = persona
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
            return self.get_persona(best_persona)
        
        # Default to Orpheus for general queries
        return self.get_persona("Orpheus")
    
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
        """Add custom persona"""
        persona = {
            "name": name,
            "description": description,
            "model": model,
            "provider": provider,
            "system_prompt": system_prompt
        }
        self.personas.append(persona)
        return persona
    
    def remove_persona(self, name: str) -> bool:
        """Remove persona by name"""
        for i, persona in enumerate(self.personas):
            if persona["name"] == name:
                self.personas.pop(i)
                return True
        return False
