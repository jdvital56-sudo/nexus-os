"""Telegram-слой: семь ботов, по одному на роль.

Каждая роль — отдельный бот со своим токеном, чтобы в списке чатов они
выглядели отдельными собеседниками, как в разобранном видео. Если отдельных
токенов нет, работает режим одного бота на всю команду: роль переключается
командой `/role`. Это позволяет попробовать систему до того, как заводить
семь ботов в BotFather.

Доступ. Бот в Telegram по умолчанию открыт всему интернету — любой, кто
узнает его имя, может ему написать. Поэтому первое, что делает каждый
обработчик, — сверяет `user_id` со списком разрешённых. Не username: его
меняют за десять секунд. Пустой список означает «никого», а не «всех».
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    constants,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import config, handoff, prompts
from .runner import Runner

logger = logging.getLogger(__name__)

# Сколько ждём нажатия кнопки подтверждения, прежде чем считать отказом.
APPROVAL_TIMEOUT = 600

# Telegram режет сообщения длиннее 4096 символов.
TELEGRAM_LIMIT = 4000

_pending: dict[str, asyncio.Future] = {}


def allowed_users() -> set[int]:
    """Кому можно писать боту. Пусто — значит никому."""
    raw = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
    out: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            out.add(int(chunk))
    return out


def is_allowed(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    permitted = allowed_users()
    if not permitted:
        logger.error(
            "TELEGRAM_ALLOWED_USER_ID пуст — бот отвечать не будет. "
            "Это защита, а не поломка: без списка бот открыт всему интернету."
        )
        return False
    if user.id not in permitted:
        logger.warning("Отклонён пользователь %s (%s)", user.id, user.username)
        return False
    return True


def split_message(text: str) -> list[str]:
    """Разбить длинный ответ по границам абзацев, а не посреди слова."""
    if len(text) <= TELEGRAM_LIMIT:
        return [text]
    parts: list[str] = []
    rest = text
    while len(rest) > TELEGRAM_LIMIT:
        cut = rest.rfind("\n\n", 0, TELEGRAM_LIMIT)
        if cut < TELEGRAM_LIMIT // 2:
            cut = rest.rfind("\n", 0, TELEGRAM_LIMIT)
        if cut < TELEGRAM_LIMIT // 2:
            cut = TELEGRAM_LIMIT
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    if rest:
        parts.append(rest)
    return parts


class RoleBot:
    """Один бот = одна роль (или все роли, если токен общий)."""

    def __init__(self, token: str, role_key: str | None) -> None:
        self.token = token
        self.fixed_role = role_key
        self.application = Application.builder().token(token).build()
        self._register()

    def _register(self) -> None:
        app = self.application
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_start))
        app.add_handler(CommandHandler("team", self.cmd_team))
        app.add_handler(CommandHandler("role", self.cmd_role))
        app.add_handler(CommandHandler("project", self.cmd_project))
        app.add_handler(CommandHandler("inbox", self.cmd_inbox))
        app.add_handler(CommandHandler("files", self.cmd_files))
        app.add_handler(CommandHandler("forget", self.cmd_forget))
        app.add_handler(CallbackQueryHandler(self.on_button))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_message))

    # --- состояние чата --------------------------------------------------

    def role_for(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        if self.fixed_role:
            return self.fixed_role
        return context.chat_data.get("role") or config.ROLES[0].key

    @staticmethod
    def project_for(context: ContextTypes.DEFAULT_TYPE) -> str:
        return context.chat_data.get("project", "")

    # --- команды ---------------------------------------------------------

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        role = config.get_role(self.role_for(context))
        hands = ", ".join(config.get_role(k).title for k in role.hands_to) or "никому"
        await update.message.reply_text(
            f"*{role.title}*\n{role.tagline}\n\n"
            f"Передаю работу: {hands}\n"
            f"Проект: `{self.project_for(context) or 'не выбран'}`\n\n"
            "Команды:\n"
            "`/project <ключ>` — задать проект\n"
            "`/inbox` — передачи мне\n"
            "`/files` — что я записал\n"
            "`/team` — вся команда\n"
            "`/forget` — начать разговор заново\n"
            + ("`/role <ключ>` — сменить роль\n" if not self.fixed_role else ""),
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    async def cmd_team(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        lines = [f"*{r.title}* (`{r.key}`)\n{r.tagline}" for r in config.ROLES]
        await update.message.reply_text(
            "\n\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN
        )

    async def cmd_role(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        if self.fixed_role:
            await update.message.reply_text("У этого бота одна роль, менять нечего.")
            return
        if not context.args:
            await update.message.reply_text(
                "Укажи ключ роли: " + ", ".join(f"`{r.key}`" for r in config.ROLES),
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            return
        try:
            role = config.get_role(context.args[0])
        except KeyError as exc:
            await update.message.reply_text(str(exc))
            return
        context.chat_data["role"] = role.key
        await update.message.reply_text(f"Теперь ты говоришь с ролью «{role.title}».")

    async def cmd_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        if not context.args:
            await update.message.reply_text(
                f"Текущий проект: `{self.project_for(context) or 'не выбран'}`",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            return
        slug = handoff.slugify(" ".join(context.args))
        context.chat_data["project"] = slug
        await update.message.reply_text(f"Проект: `{slug}`", parse_mode=constants.ParseMode.MARKDOWN)

    async def cmd_inbox(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        items = handoff.pending(self.role_for(context))
        if not items:
            await update.message.reply_text("Непринятых передач нет.")
            return
        lines = []
        for item in items:
            meta = item["meta"]
            source = config.BY_KEY.get(meta.get("from_role", ""))
            lines.append(
                f"• `{item['handoff_id']}`\n  проект `{meta.get('project', '?')}`, "
                f"от {source.title if source else '?'}"
            )
        await update.message.reply_text(
            "\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN
        )

    async def cmd_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        from .workspace import Workspace

        ws = Workspace(self.role_for(context))
        found = ws.search("docs/**/*.md", limit=40)
        await update.message.reply_text(
            "\n".join(f"`{p}`" for p in found) if found else "Пока ничего не записано.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    async def cmd_forget(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return
        Runner(self.role_for(context), str(update.effective_chat.id)).forget()
        await update.message.reply_text(
            "История разговора очищена. Файлы на диске остались — они и есть память."
        )

    # --- подтверждения ---------------------------------------------------

    async def on_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not is_allowed(update):
            await query.answer("Нет доступа.")
            return
        await query.answer()
        action, _, token = (query.data or "").partition(":")
        future = _pending.get(token)
        if future is None or future.done():
            await query.edit_message_text("Запрос уже неактуален.")
            return
        future.set_result(action == "yes")
        try:
            await query.edit_message_text(
                (query.message.text or "")
                + ("\n\n✅ Подтверждено" if action == "yes" else "\n\n⛔ Отказано")
            )
        except Exception:
            logger.debug("Не смог отметить решение в сообщении", exc_info=True)

    def make_approver(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        async def approve(title: str, details: str) -> bool:
            token = uuid.uuid4().hex[:12]
            future: asyncio.Future = asyncio.get_running_loop().create_future()
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Разрешить", callback_data=f"yes:{token}"),
                        InlineKeyboardButton("⛔ Отказать", callback_data=f"no:{token}"),
                    ]
                ]
            )
            # Без разметки намеренно. В `details` попадает команда оболочки, а
            # обратная кавычка или звёздочка в ней роняют отправку с
            # BadRequest. Хуже того, разметка меняет вид текста, который
            # человек утверждает: он должен видеть команду ровно такой, какая
            # выполнится.
            _pending[token] = future
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{title}\n\n{details}",
                    reply_markup=keyboard,
                )
            except Exception:
                # Не смогли спросить — значит нельзя. Молчаливое разрешение
                # здесь было бы худшим из возможных исходов.
                _pending.pop(token, None)
                logger.exception("Не смог отправить запрос подтверждения")
                return False
            try:
                return await asyncio.wait_for(future, timeout=APPROVAL_TIMEOUT)
            except asyncio.TimeoutError:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Не дождался ответа — считаю отказом.",
                )
                return False
            finally:
                _pending.pop(token, None)

        return approve

    # --- основной обработчик ---------------------------------------------

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_allowed(update):
            return

        chat_id = update.effective_chat.id
        role_key = self.role_for(context)
        runner = Runner(role_key, str(chat_id))

        status = await update.message.reply_text("⏳ Работаю…")
        last_status = {"text": ""}
        tool_lines: list[str] = []

        async def on_status(text: str) -> None:
            if text == last_status["text"]:
                return
            last_status["text"] = text
            shown = text + ("\n\n" + "\n".join(tool_lines[-6:]) if tool_lines else "")
            try:
                await status.edit_text(shown[:TELEGRAM_LIMIT])
            except Exception:  # сообщение не изменилось / удалено — не важно
                logger.debug("Не смог обновить статус", exc_info=True)

        def on_tool(_name: str, line: str) -> None:
            tool_lines.append(line)

        await context.bot.send_chat_action(chat_id, constants.ChatAction.TYPING)

        result = await runner.run(
            update.message.text,
            project=self.project_for(context),
            on_status=on_status,
            on_tool=on_tool,
            approve=self.make_approver(chat_id, context),
        )

        trace = "\n".join(tool_lines[-10:])
        try:
            await status.edit_text(
                (trace or "Без вызовов инструментов")[:TELEGRAM_LIMIT]
            )
        except Exception:
            logger.debug("Не смог показать трассу", exc_info=True)

        # Предупреждение показывает код, а не модель: живой прогон показал,
        # что агент может подброшенную команду не выполнить, но и промолчать.
        if result.warnings:
            lines = "\n".join(f"• {w}" for w in result.warnings[:5])
            await update.message.reply_text(
                "⚠️ В чужих данных найдены строки, похожие на команды агенту. "
                "Агент их не выполнял, но проверь, откуда они:\n\n" + lines
            )

        for chunk in split_message(result.text):
            await update.message.reply_text(chunk)

        await self._send_images(update, context, role_key, result.files)

        footer = (
            f"_{result.iterations} шагов · {result.seconds:.0f} с · "
            f"${result.cost_usd:.4f}_"
        )
        if result.stopped_by:
            footer += f" · остановлен: {result.stopped_by}"
        await update.message.reply_text(footer, parse_mode=constants.ParseMode.MARKDOWN)

    async def _send_images(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        role_key: str,
        files: list[str],
    ) -> None:
        """Сгенерированные кадры человек должен увидеть, а не открывать папку."""
        from .workspace import Workspace

        ws = Workspace(role_key)
        for relative in files:
            if not relative.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            try:
                path = ws.resolve(relative)
            except Exception:
                continue
            if not path.is_file():
                continue
            try:
                with path.open("rb") as stream:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=stream,
                        caption=relative,
                    )
            except Exception:
                logger.warning("Не смог отправить %s", relative, exc_info=True)


def configured_bots() -> list[tuple[str, str | None]]:
    """Пары (токен, роль). Роль `None` — один бот на всю команду."""
    pairs: list[tuple[str, str | None]] = []
    for role in config.ROLES:
        token = os.getenv(role.env_token, "").strip()
        if token:
            pairs.append((token, role.key))
    if pairs:
        return pairs
    shared = os.getenv("CREW_TOKEN_ALL", "").strip()
    return [(shared, None)] if shared else []


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    # httpx пишет в INFO полный URL запроса, а в нём токен бота — так все
    # токены команды оседали открытым текстом в crew_stderr.log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main() -> None:
    setup_logging()
    config.ensure_layout()
    prompts.reload()

    pairs = configured_bots()
    if not pairs:
        raise SystemExit(
            "Нет ни одного токена. Заведи ботов в @BotFather и положи токены в .env:\n"
            + "\n".join(f"  {r.env_token}=...   # {r.title}" for r in config.ROLES)
            + "\n\nИли один общий бот на всю команду:\n  CREW_TOKEN_ALL=..."
        )
    if not allowed_users():
        raise SystemExit(
            "TELEGRAM_ALLOWED_USER_ID пуст. Без него бот открыт всему интернету — "
            "запуск остановлен намеренно. Укажи свой числовой Telegram user id."
        )

    # Движок проверяем здесь, а не на первом сообщении: иначе человек напишет
    # боту, увидит «модель недоступна» и пойдёт искать причину в Telegram.
    from backend.services.llm import get_llm_service
    from .runner import EngineNotReady, check_engine

    llm = get_llm_service()
    try:
        check_engine(llm)
    except EngineNotReady as exc:
        raise SystemExit(str(exc)) from exc
    logger.info("Движок: %s/%s", llm.provider, llm.model)

    bots = [RoleBot(token, role_key) for token, role_key in pairs]
    for bot, (_, role_key) in zip(bots, pairs):
        title = config.get_role(role_key).title if role_key else "вся команда"
        logger.info("Запускаю бота: %s", title)

    async def run_all() -> None:
        for bot in bots:
            await bot.application.initialize()
            await bot.application.start()
            await bot.application.updater.start_polling(drop_pending_updates=True)
        logger.info("Команда на связи. Ctrl+C для остановки.")
        await asyncio.Event().wait()

    try:
        asyncio.run(run_all())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка.")


if __name__ == "__main__":
    main()
