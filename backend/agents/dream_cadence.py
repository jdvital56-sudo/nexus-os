"""
Dream Cadence - Night Analytics System
Runs automated analysis during sleep hours and delivers morning brief
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.core.config import settings
from backend.services.llm import LLMService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DreamCadence:
    """
    Night analytics system that runs during sleep hours
    Analyzes 8 dimensions of activity and generates morning brief
    """
    
    ANALYSIS_DIMENSIONS = [
        "Cost Intelligence",           # API cost analysis
        "Conversation & Context Drift", # Context loss detection
        "Skill Performance",           # Tool/skill effectiveness
        "Memory Hygiene",              # Memory cleanup needs
        "Workflow Patterns",           # Automation opportunities
        "Session Hygiene",             # Stale session cleanup
        "External Opportunities",      # New optimization points
        "Business Outcomes"            # Progress toward goals
    ]
    
    def __init__(self):
        self.llm = LLMService()
        self.scheduler = AsyncIOScheduler()
        self.cron_schedule = os.getenv("NIGHT_ANALYSIS_CRON", "0 3 * * *")
        
        # Parse cron schedule
        parts = self.cron_schedule.split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
            self.trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week
            )
        else:
            logger.warning(f"Invalid cron schedule: {self.cron_schedule}, using default 3 AM")
            self.trigger = CronTrigger(hour=3, minute=0)
    
    async def analyze_cost_intelligence(self) -> str:
        """Analyze API costs across all providers"""
        prompt = """
Проанализируй расходы на API за последние 24 часа:
- DeepSeek: стоимость запросов
- Claude/OpenAI: стоимость запросов  
- Gemini: стоимость запросов
- Apollo: стоимость запросов

Выяви аномалии и предложи оптимизации.
Формат: Краткий список с цифрами.
        """
        return await self.llm.generate_response(prompt)
    
    async def analyze_context_drift(self) -> str:
        """Detect context loss in long conversations"""
        prompt = """
Проанализиуй диалоги за 24 часа на предмет потери контекста:
- Были ли важные темы упущены?
- Требуется ли повторение ключевой информации?
- Какие контексты нужно сохранить в долгосрочную память?

Формат: Список рекомендаций.
        """
        return await self.llm.generate_response(prompt)
    
    async def analyze_skill_performance(self) -> str:
        """Evaluate skill/tool effectiveness"""
        prompt = """
Оцени эффективность использованных скиллов за 24 часа:
- Какие скиллы работали хорошо?
- Какие дали сбои или неточные результаты?
- Какие новые скиллы стоит добавить?

Формат: Таблица с оценками 1-10.
        """
        return await self.llm.generate_response(prompt)
    
    async def analyze_memory_hygiene(self) -> str:
        """Identify memory cleanup needs"""
        prompt = """
Проанализируй хранилище памяти:
- Какие воспоминания устарели (>30 дней)?
- Какие дубликаты можно удалить?
- Что важно сохранить навсегда?

Формат: Список действий по зачистке.
        """
        return await self.llm.generate_response(prompt)
    
    async def analyze_workflow_patterns(self) -> str:
        """Find automation opportunities"""
        prompt = """
Выяви повторяющиеся паттерны в действиях за 24 часа:
- Какие действия выполнялись многократно?
- Что можно автоматизировать через скрипты?
- Какие workflow можно оптимизировать?

Формат: Топ-3 возможности для автоматизации.
        """
        return await self.llm.generate_response(prompt)
    
    async def analyze_session_hygiene(self) -> str:
        """Clean up stale sessions"""
        prompt = """
Проанализируй активные сессии:
- Какие сессии зависли (>24 часов без активности)?
- Какие можно безопасно закрыть?
- Есть ли утечки ресурсов?

Формат: Список сессий для закрытия.
        """
        return await self.llm.generate_response(prompt)
    
    async def analyze_external_opportunities(self) -> str:
        """Find new optimization opportunities"""
        prompt = """
Ищи внешние возможности для улучшения:
- Новые API или сервисы для интеграции?
- Обновления моделей LLM для лучшего качества/цены?
- Тренды в AI-инструментах?

Формат: Список возможностей с приоритетами.
        """
        return await self.llm.generate_response(prompt)
    
    async def analyze_business_outcomes(self) -> str:
        """Assess progress toward goals"""
        prompt = """
Оцени прогресс к глобальным целям за 24 часа:
- Какие задачи продвинули к цели?
- Какие были отвлечения?
- Какой общий прогресс (% за неделю/месяц)?

Формат: Краткая сводка с метриками.
        """
        return await self.llm.generate_response(prompt)
    
    async def run_full_analysis(self) -> Dict[str, str]:
        """Run all 8 analyses"""
        logger.info("🌙 Starting Dream Cadence night analysis...")
        
        results = {}
        
        try:
            # Run all analyses in parallel for speed
            tasks = [
                self.analyze_cost_intelligence(),
                self.analyze_context_drift(),
                self.analyze_skill_performance(),
                self.analyze_memory_hygiene(),
                self.analyze_workflow_patterns(),
                self.analyze_session_hygiene(),
                self.analyze_external_opportunities(),
                self.analyze_business_outcomes()
            ]
            
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results_list):
                dimension = self.ANALYSIS_DIMENSIONS[i]
                if isinstance(result, Exception):
                    results[dimension] = f"⚠️ Ошибка анализа: {str(result)}"
                    logger.error(f"Error analyzing {dimension}: {result}")
                else:
                    results[dimension] = result
            
            logger.info("✅ Night analysis completed")
            
        except Exception as e:
            logger.error(f"Dream Cadence analysis failed: {e}")
            results["error"] = str(e)
        
        return results
    
    async def generate_morning_brief(self, analysis_results: Dict[str, str]) -> str:
        """Generate concise morning brief from analysis results"""
        
        brief_prompt = f"""
На основе ночного анализа создай утренний бриф.

РЕЗУЛЬТАТЫ АНАЛИЗА:
{chr(10).join(f"**{k}**:{chr(10)}{v}" for k, v in analysis_results.items())}

ЗАДАЧА:
Создай краткий утренний бриф (максимум 300 слов) включающий:
1. 🌅 Приветствие и дата
2. ✅ 3 главных достижения за вчера
3. ⚠️ 2 проблемы требующие внимания
4. 🎯 2-3 конкретных действия на сегодня
5. 💡 Одна идея для оптимизации

Тон: Мотивирующий, конкретный, без воды.
Формат: Markdown с эмодзи.
        """
        
        return await self.llm.generate_response(brief_prompt)
    
    async def send_brief_to_telegram(self, brief: str):
        """Send morning brief to Telegram (if configured)"""
        try:
            from telegram import Bot
            bot_token = settings.telegram_bot_token
            chat_id = settings.telegram_allowed_user_id
            
            if bot_token and chat_id:
                bot = Bot(token=bot_token)
                await bot.send_message(chat_id=chat_id, text=brief, parse_mode="Markdown")
                logger.info("📱 Morning brief sent to Telegram")
            else:
                logger.warning("Telegram not configured, saving brief to file")
                self.save_brief_to_file(brief)
        except Exception as e:
            logger.error(f"Failed to send Telegram brief: {e}")
            self.save_brief_to_file(brief)
    
    def save_brief_to_file(self, brief: str):
        """Save brief to file as fallback"""
        artifacts_path = os.getenv("HERMES_ARTIFACTS_PATH", "./artifacts")
        os.makedirs(artifacts_path, exist_ok=True)
        
        filename = f"{artifacts_path}/brief_{datetime.now().strftime('%Y-%m-%d')}.md"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Утренний бриф\n")
            f.write(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(brief)
        
        logger.info(f"💾 Brief saved to {filename}")
    
    async def nightly_job(self):
        """Main nightly job: analyze + brief"""
        analysis_results = await self.run_full_analysis()
        brief = await self.generate_morning_brief(analysis_results)
        await self.send_brief_to_telegram(brief)
    
    def start(self):
        """Start the scheduler"""
        self.scheduler.add_job(
            self.nightly_job,
            trigger=self.trigger,
            id='dream_cadence',
            name='Night Analytics',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info(f"🌙 Dream Cadence scheduled: {self.cron_schedule}")
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Dream Cadence stopped")


# Singleton instance
dream_cadence = DreamCadence()


def start_dream_cadence():
    """Start Dream Cadence scheduler"""
    dream_cadence.start()


def stop_dream_cadence():
    """Stop Dream Cadence scheduler"""
    dream_cadence.stop()
