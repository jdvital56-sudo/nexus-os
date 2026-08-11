"""
Hermes Agent - Telegram Interface for NEXSYS
Acts as the mobile communication bridge to the main AI system
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from backend.core.config import settings
from backend.services.llm import LLMService, TranscriptionUnavailable
from backend.services.apollo_client import ApolloClient
from backend.services.google_calendar import GoogleCalendarClient
from backend.services.conversation import ConversationService
from backend.agents.persona_manager import PersonaManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HermesAgent:
    """
    Hermes Agent - Telegram interface for NEXSYS
    Handles voice/text commands from mobile and routes to appropriate agents
    """
    
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.allowed_user_id = settings.telegram_allowed_user_id
        self.llm = LLMService()
        self.apollo = ApolloClient() if settings.apollo_api_key else None
        self.calendar = GoogleCalendarClient()
        self.persona_manager = PersonaManager()
        # Мышление живёт в ConversationService, бот только принимает и отдаёт (I-1)
        self.conversation = ConversationService(
            llm=self.llm, persona_manager=self.persona_manager
        )
        self.application = None
        
        # Context compression settings
        self.compression_threshold = float(os.getenv("CONTEXT_COMPRESSION_THRESHOLD", "0.8"))
        
        # Paths
        self.obsidian_vault = os.getenv("OBSIDIAN_VAULT_PATH", "")
        self.artifacts_path = os.getenv("HERMES_ARTIFACTS_PATH", "./artifacts")
        
        os.makedirs(self.artifacts_path, exist_ok=True)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not self._authorize_user(update.effective_user.id):
            await update.message.reply_text("⛔ Unauthorized access")
            return
        
        await update.message.reply_text(
            "👋 Привет! Я Hermes, твой AI-ассистент.\n\n"
            "Доступные команды:\n"
            "/start - Запустить бота\n"
            "/status - Статус системы\n"
            "/persons - Список персон\n"
            "/brief - Утренний бриф\n"
            "/help - Помощь\n\n"
            "Просто отправь мне сообщение или голосовую заметку!"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        help_text = """
📚 **Помощь Hermes**

**Команды:**
- /start - Запуск бота
- /status - Проверка статуса системы
- /persons - Показать доступные AI-персоны
- /brief - Получить утренний бриф (Dream Cadence)
- /help - Эта справка

**Примеры запросов:**
- "Найди 20 кровельных компаний в Техасе"
- "Создай план проекта для..."
- "Запиши встречу с командой на завтра в 15:00"
- "Проанализируй мои расходы за неделю"

**Персоны:**
- Mercury - Автономные скрипты (Llama 3.3)
- Philosopher - Глубокий анализ (Claude Opus)
- Labyrinth - Исследования (GPT/DeepSeek)
- Orpheus - Общая аналитика
        """
        await update.message.reply_text(help_text)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        status = {
            "LLM": "✅" if settings.llm_api_key else "❌",
            "Apollo": "✅" if settings.apollo_api_key else "❌",
            "Google Calendar": "✅" if os.path.exists("credentials.json") else "❌",
            "Obsidian Vault": "✅" if os.path.exists(self.obsidian_vault) else "❌",
            "Compression": f"{self.compression_threshold:.2f}"
        }
        
        status_text = "🔧 **Статус системы:**\n\n"
        for service, state in status.items():
            status_text += f"{service}: {state}\n"
        
        await update.message.reply_text(status_text)
    
    async def persons_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /persons command - Show available personas"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        personas = self.persona_manager.list_personas()
        text = "🎭 **Доступные персоны:**\n\n"
        for p in personas:
            text += f"**{p['name']}**: {p['description']}\n"
            text += f"  Модель: {p['model']}\n\n"
        
        await update.message.reply_text(text)
    
    async def brief_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /brief command - Morning briefing from Dream Cadence"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        # Generate morning brief using LLM
        prompt = """
Сгенерируй утренний бриф на основе вчерашней активности.
Включи:
1. Краткую сводку выполненных задач
2. Анализ расходов на API
3. 2-3 конкретных действия на сегодня
4. Любые важные уведомления

Формат: Кратко, по делу, с эмодзи.
        """
        
        try:
            brief = await self.llm.generate_response(prompt)
            await update.message.reply_text(f"🌅 **Утренний бриф:**\n\n{brief}")
        except Exception as e:
            logger.error(f"Error generating brief: {e}")
            await update.message.reply_text("⚠️ Не удалось сгенерировать бриф. Проверьте логи.")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        user_message = update.message.text
        logger.info(f"Received message from {update.effective_user.username}: {user_message}")

        try:
            response = await self.conversation.handle(
                channel="telegram",
                user_id=str(update.effective_user.id),
                text=user_message,
            )
            await update.message.reply_text(response)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text("⚠️ Произошла ошибка при обработке запроса.")
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages - transcribe and process"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        voice_file = await update.message.voice.get_file()
        voice_path = f"{self.artifacts_path}/voice_{update.message.message_id}.ogg"
        await voice_file.download_to_drive(voice_path)
        
        logger.info(f"Received voice message, saved to {voice_path}")
        
        # Transcribe using Gemini (multimodal)
        try:
            transcription = await self.llm.transcribe_audio(voice_path)
            await update.message.reply_text(f"🎤 **Распознано:**\n{transcription}")

            # Расшифровка идёт тем же путём, что и текст
            response = await self.conversation.handle(
                channel="telegram",
                user_id=str(update.effective_user.id),
                text=transcription,
            )
            await update.message.reply_text(response)

        except TranscriptionUnavailable as e:
            # Честная причина вместо «что-то пошло не так»
            logger.warning(f"Voice transcription disabled: {e}")
            await update.message.reply_text(
                f"🎤 {e}.\nДобавьте ключ в .env или пришлите текстом."
            )
        except Exception as e:
            logger.error(f"Error processing voice: {e}")
            await update.message.reply_text("⚠️ Не удалось распознать голосовое сообщение.")
        finally:
            # Cleanup
            if os.path.exists(voice_path):
                os.remove(voice_path)
    
    def _authorize_user(self, user_id: int) -> bool:
        """Check if user is authorized"""
        if not self.allowed_user_id:
            return True  # No restriction if not configured
        return str(user_id) == str(self.allowed_user_id)
    
    async def run(self):
        """Start the Telegram bot"""
        if not self.bot_token:
            logger.error("Telegram bot token not configured. Set TELEGRAM_BOT_TOKEN in .env")
            return
        
        self.application = Application.builder().token(self.bot_token).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("persons", self.persons_command))
        self.application.add_handler(CommandHandler("brief", self.brief_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        
        logger.info("🚀 Hermes Agent started. Listening for messages...")
        await self.application.run_polling(allowed_updates=Update.ALL_TYPES)


async def main():
    hermes = HermesAgent()
    await hermes.run()


if __name__ == "__main__":
    asyncio.run(main())
