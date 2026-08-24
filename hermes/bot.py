"""
Hermes Agent - Telegram Interface for NEXSYS
Acts as the mobile communication bridge to the main AI system
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Корень проекта в путь — иначе `python hermes/bot.py` не находит backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update, Bot
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ContextTypes
)

from backend.core.config import settings
from backend.services.llm import LLMService, TranscriptionUnavailable
from backend.services.apollo_client import ApolloClient
from backend.services.google_calendar import GoogleCalendarClient
from backend.services.conversation import ConversationService
from backend.agents.persona_manager import PersonaManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# httpx логирует полный URL запроса, а туда входит токен бота — в INFO
# он утекал бы в консоль и в nexus.log при каждом опросе Telegram
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# Чистка разметки живёт в backend/services/textclean.py: ею пользуются
# Телеграм, веб-чат и озвучка. Раньше копия была только здесь, и веб-чат
# с голосом её не видели — модель ставила звёздочки, а синтезатор читал
# их вслух: «звёздочка звёздочка автохоткей».
from backend.services.textclean import strip_markdown  # noqa: E402


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

        # Paths
        self.obsidian_vault = os.getenv("OBSIDIAN_VAULT_PATH", "")
        self.artifacts_path = os.getenv("HERMES_ARTIFACTS_PATH", "./artifacts")
        
        os.makedirs(self.artifacts_path, exist_ok=True)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        # Чужому не отвечаем ничего — как и все остальные обработчики.
        # Ответ «Unauthorized» подтверждал бы постороннему, что бот жив;
        # отказ виден в логах, там его и надо искать при диагностике.
        if not self._authorize_user(update.effective_user.id):
            return

        await update.message.reply_text(
            "👋 Привет! Я Hermes, твой AI-ассистент.\n\n"
            "Доступные команды:\n"
            "/start - Запустить бота\n"
            "/status - Статус системы\n"
            "/persons - Список персон\n"
            "/brief - Утренний бриф\n"
            "/services - Мои платные сервисы\n"
            "/reset - Начать разговор заново\n"
            "/help - Помощь\n\n"
            "Просто отправь мне сообщение или голосовую заметку!"
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        help_text = """
📚 Помощь Hermes

Команды:
- /start - Запуск бота
- /status - Проверка статуса системы
- /persons - Показать доступные AI-персоны
- /brief - Получить утренний бриф (Dream Cadence)
- /reset - Забыть нить разговора (память фактов останется)
- /help - Эта справка

Примеры запросов:
- "Найди 20 кровельных компаний в Техасе"
- "Создай план проекта для..."
- "Запиши встречу с командой на завтра в 15:00"
- "Проанализируй мои расходы за неделю"

Персоны:
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
        }
        
        status_text = "🔧 Статус системы:\n\n"
        for service, state in status.items():
            status_text += f"{service}: {state}\n"
        
        await update.message.reply_text(status_text)
    
    async def persons_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /persons command - Show available personas"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        personas = self.persona_manager.list_personas()
        text = "🎭 Доступные персоны:\n\n"
        for p in personas:
            text += f"{p['name']}: {p['description']}\n"
            text += f"  Модель: {p['model']}\n\n"
        
        await update.message.reply_text(text)
    
    async def brief_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /brief command — читает кэш ночного прогона.

        Полный анализ в чате занимал бы десятки секунд и стоил бы денег
        при каждом вызове (риск R-10), поэтому пишет ночь, а читает /brief.
        """
        if not self._authorize_user(update.effective_user.id):
            return

        from backend.services import dream as dream_store

        cached = dream_store.get_brief()
        if not cached:
            await update.message.reply_text(
                "🌅 Ночной прогон Dream Cadence ещё не выполнялся.\n"
                "Он запускается по расписанию (по умолчанию в 3:00)."
            )
            return

        findings = dream_store.list_findings(status=dream_store.STATUS_NEW)
        tail = (
            f"\n\n📋 Новых находок: {len(findings)} — посмотреть в Dream Review."
            if findings else ""
        )
        await update.message.reply_text(
            f"🌅 Утренний бриф (прогон {cached['run_id']}):\n\n{cached['brief']}{tail}"
        )
    
    async def reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /reset — начать разговор с чистого листа.

        Стирается только нить последних реплик. Память фактов и база знаний
        остаются: «сменить тему» и «забудь, что я говорил» — разные просьбы.
        """
        if not self._authorize_user(update.effective_user.id):
            return

        from backend.services import dialog_history

        removed = dialog_history.clear("telegram", str(update.effective_user.id))
        if removed:
            await update.message.reply_text(
                f"🧹 Нить разговора очищена ({removed} реплик).\n"
                "Память фактов и заметки не тронуты."
            )
        else:
            await update.message.reply_text("🧹 Нить разговора и так пуста.")

    async def handle_content_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Кнопки «Одобрить»/«Отклонить» под черновиком контент-завода.

        Бот здесь только транспорт: решение применяет
        backend.services.content_approval, чтобы то же самое действие из
        интерфейса шло по тем же правилам.
        """
        query = update.callback_query
        if not self._authorize_user(query.from_user.id):
            await query.answer("Не для вас.", show_alert=True)
            return

        from backend.services import content_approval

        parsed = content_approval.parse_callback(query.data)
        if parsed is None:
            return  # чужая кнопка — не наше дело

        action, item_id = parsed
        await query.answer()
        try:
            reply = await content_approval.apply(action, item_id)
        except Exception as e:
            logger.exception("Не удалось применить решение по черновику %s", item_id)
            reply = f"Не удалось применить решение: {e}"

        # Правим само сообщение, а не шлём новое: кнопки должны исчезнуть,
        # иначе по ним можно нажать повторно и получить второй ответ.
        try:
            await query.edit_message_text(f"{query.message.text}\n\n{reply}")
        except Exception:
            await query.message.reply_text(reply)

    async def services_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /services — за что платим и когда спишут."""
        if not self._authorize_user(update.effective_user.id):
            return

        from backend.services import wallet

        summary = wallet.summary()
        if not summary["active_count"]:
            await update.message.reply_text(
                "💳 Реестр сервисов пуст.\n"
                "Добавьте подписки — и я буду напоминать о списаниях "
                "и следить за балансами там, где это возможно."
            )
            return

        lines = [
            f"💳 Активных сервисов: {summary['active_count']}",
            f"В месяц уходит: ~${summary['monthly_total_usd']}",
            "",
        ]
        for s in wallet.list_services():
            money = f"${s['cost']} {s['period']}" if s["cost"] else s["period"]
            when = f", списание {s['next_charge']}" if s.get("next_charge") else ", дата списания неизвестна"
            bal = f", остаток ${s['balance']}" if s.get("balance") is not None else ""
            lines.append(f"- {s['name']}: {money}{when}{bal}")

        if summary["due_soon"]:
            lines += ["", "⏰ Скоро списание:"]
            for s in summary["due_soon"]:
                d = s["days_left"]
                when = "сегодня" if d == 0 else (f"через {d} дн." if d > 0 else f"просрочено на {-d} дн.")
                cancel = f" — отменить: {s['cancel_url']}" if s.get("cancel_url") else ""
                lines.append(f"- {s['name']}: {when}{cancel}")

        if summary["low_balance"]:
            lines += ["", "🪫 Баланс на исходе:"]
            for s in summary["low_balance"]:
                lines.append(f"- {s['name']}: ${s['balance']}")

        await update.message.reply_text("\n".join(lines))

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
            await update.message.reply_text(strip_markdown(response))
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text("⚠️ Произошла ошибка при обработке запроса.")
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages - transcribe and process"""
        if not self._authorize_user(update.effective_user.id):
            return
        
        voice_file = await update.message.voice.get_file()
        # Скачанное голосовое — мусор процесса, а не артефакт: кладём в
        # служебную подпапку, чтобы не засорять то, что человек будет читать
        from backend.services import artifacts

        voice_path = str(artifacts.temp_dir() / f"voice_{update.message.message_id}.ogg")
        await voice_file.download_to_drive(voice_path)
        
        logger.info(f"Received voice message, saved to {voice_path}")
        
        # Transcribe using Gemini (multimodal)
        try:
            transcription = await self.llm.transcribe_audio(voice_path)
            await update.message.reply_text(f"🎤 Распознано:\n{transcription}")

            # Расшифровка идёт тем же путём, что и текст
            response = await self.conversation.handle(
                channel="telegram",
                user_id=str(update.effective_user.id),
                text=transcription,
            )
            await update.message.reply_text(strip_markdown(response))

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
        """Check if user is authorized.

        Отказ виден в логах: пользователю бот молчит по хартии, но
        «бот не запущен» и «вас нет в списке» обязаны различаться при
        диагностике — иначе тишина неотличима от поломки.
        """
        if not self.allowed_user_id:
            return True  # No restriction if not configured
        if str(user_id) != str(self.allowed_user_id):
            logger.warning(
                "Сообщение от %s отклонено: в TELEGRAM_ALLOWED_USER_ID указан %s",
                user_id,
                self.allowed_user_id,
            )
            return False
        return True
    
    def run(self):
        """Start the Telegram bot.

        run_polling() сам создаёт и закрывает цикл событий, поэтому метод
        синхронный: под asyncio.run() библиотека падает на закрытии цикла.
        """
        if not self.bot_token:
            logger.error("Telegram bot token not configured. Set TELEGRAM_BOT_TOKEN in .env")
            return

        # Второй экземпляр молча выходит, а не дерётся с первым за
        # getUpdates — Telegram разрешает только один активный опрос на
        # токен, и без этой проверки оба падали с Conflict (18.08.2026:
        # так столкнулись наблюдатель в start_all.ps1 и ручной запуск).
        from backend.core import singleton

        if not singleton.acquire_bot_lock():
            logger.warning("Другой экземпляр Гермеса уже слушает Telegram — этот выходит.")
            return

        self.application = Application.builder().token(self.bot_token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("persons", self.persons_command))
        self.application.add_handler(CommandHandler("brief", self.brief_command))
        self.application.add_handler(CommandHandler("services", self.services_command))
        self.application.add_handler(CommandHandler("reset", self.reset_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_content_button))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))

        logger.info("Hermes Agent started. Listening for messages...")
        try:
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        finally:
            singleton.release_bot_lock()


def main():
    HermesAgent().run()


if __name__ == "__main__":
    main()
