"""Dream Cadence — ночная аналитика Nexus OS.

Восемь измерений анализа. Каждое получает реальные данные системы, а не
пустой промпт: иначе модель просто сочиняет цифры. Результат — находки с
идентификатором и статусом, которые человек принимает или отклоняет
вручную (I-2). Ночной прогон — фоновая нагрузка, он обязан уступать
дневному бюджету (I-4) и жить в том же процессе, что и API (I-3).
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.core import eventbus
from backend.core.config import settings
from backend.services import budget, dream as dream_store
from backend.services.llm import LLMService

logger = logging.getLogger(__name__)

# Сколько фактов INBOX показываем модели за один прогон
_INBOX_SAMPLE = 40

_FINDINGS_PROMPT = """Ты аналитик системы Nexus OS. Измерение анализа: {dimension}.

Данные системы:
{context}

Опираясь ТОЛЬКО на эти данные, выдели проблемы и возможности.
Не выдумывай цифры, которых нет в данных. Если данных недостаточно
или всё в порядке — верни пустой список.

Верни СТРОГО JSON без пояснений:
{{"findings": [{{"title": "...", "detail": "...", "severity": "low|medium|high"}}]}}"""

_HYGIENE_PROMPT = """Ты отвечаешь за гигиену памяти Nexus OS.

Ниже факты из слоя INBOX — это карантин, куда попадает всё новое.
Твоя задача: решить, что заслуживает продвижения в OPERATIONAL (рабочие
сведения, которые пригодятся снова), а что — просто шум диалога.

Факты:
{context}

Верни СТРОГО JSON без пояснений:
{{"promote": [{{"fact_id": "...", "reason": "..."}}],
  "noise": [{{"fact_id": "...", "reason": "..."}}]}}

Продвигай экономно: только то, что реально стоит помнить завтра."""


def _parse_json(raw: str) -> dict:
    """Модели любят обернуть JSON в ```json или болтовню — достаём его."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        logger.warning("Ответ модели не разобран как JSON")
        return {}


class DreamCadence:
    """Ночной анализ по восьми измерениям с персистентными находками."""

    ANALYSIS_DIMENSIONS = [
        "Cost Intelligence",
        "Conversation & Context Drift",
        "Skill Performance",
        "Memory Hygiene",
        "Workflow Patterns",
        "Session Hygiene",
        "External Opportunities",
        "Business Outcomes",
    ]

    def __init__(self, llm: LLMService | None = None):
        self.llm = llm or LLMService()
        self.scheduler = AsyncIOScheduler()
        self.cron_schedule = os.getenv("NIGHT_ANALYSIS_CRON", "0 3 * * *")

        parts = self.cron_schedule.split()
        if len(parts) == 5:
            minute, hour, day, month, day_of_week = parts
            self.trigger = CronTrigger(
                minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
            )
        else:
            logger.warning("Некорректный cron '%s', беру 3:00", self.cron_schedule)
            self.trigger = CronTrigger(hour=3, minute=0)

    # --- Сбор реальных данных ---

    def _collect(self, dimension: str) -> str:
        """Реальные данные системы для измерения. Пусто — значит анализировать нечего."""
        from backend.services import graph as graph_svc
        from backend.services import memory as memory_svc
        from backend.services import skills as skills_svc
        from backend.services import tasks as task_svc

        try:
            if dimension == "Cost Intelligence":
                status = budget.status()
                return (
                    f"Потрачено сегодня: ${status['spent_usd']}\n"
                    f"Дневной бюджет: ${status['budget_usd']}\n"
                    f"Предохранитель сработал: {status['throttled']}"
                )

            if dimension == "Conversation & Context Drift":
                facts = memory_svc.get_facts(tags=["dialog"], limit=30)
                if not facts:
                    return ""
                return "\n".join(f"- [{f.source}] {f.content[:200]}" for f in facts)

            if dimension == "Skill Performance":
                skills = skills_svc.list_skills()
                if not skills:
                    return ""
                return "\n".join(
                    f"- {s['id']}: {s['name']}, шагов {s['steps']}, категория {s['category']}"
                    for s in skills
                )

            if dimension == "Workflow Patterns":
                facts = memory_svc.get_facts(limit=50)
                if not facts:
                    return ""
                tags: dict[str, int] = {}
                for f in facts:
                    for t in f.tags:
                        tags[t] = tags.get(t, 0) + 1
                return "Частота тегов памяти: " + ", ".join(
                    f"{k}={v}" for k, v in sorted(tags.items(), key=lambda x: -x[1])
                )

            if dimension == "Session Hygiene":
                stats = graph_svc.get_stats()
                mem = memory_svc.get_stats()
                return (
                    f"Граф: узлов {stats.nodes}, рёбер {stats.edges}, "
                    f"компонент связности {stats.connected_components}\n"
                    f"Память: {mem}"
                )

            if dimension == "Business Outcomes":
                tasks = task_svc.list_tasks()
                if not tasks:
                    return ""
                by_status: dict[str, int] = {}
                for t in tasks:
                    by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
                return f"Задачи по статусам: {by_status}\nВсего: {len(tasks)}"

            if dimension == "External Opportunities":
                # Локальных данных нет — измерение опирается на знания модели,
                # поэтому находки помечаются низкой важностью
                return "Внешних данных в системе нет."
        except Exception:
            logger.exception("Не удалось собрать данные для '%s'", dimension)

        return ""

    # --- Анализ ---

    async def analyze_dimension(self, run_id: str, dimension: str) -> List[dict]:
        """Одно измерение: собрать данные, спросить модель, записать находки."""
        if dimension == "Memory Hygiene":
            return await self.analyze_memory_hygiene(run_id)

        context = self._collect(dimension)
        if not context:
            logger.info("Измерение '%s' пропущено: нет данных", dimension)
            return []

        raw = await self.llm.generate_response(
            _FINDINGS_PROMPT.format(dimension=dimension, context=context),
            kind=budget.BACKGROUND,
            json_mode=True,
        )
        parsed = _parse_json(raw)
        findings = []
        for item in parsed.get("findings", [])[:5]:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            finding = dream_store.add_finding(
                run_id=run_id,
                dimension=dimension,
                title=str(item["title"]),
                detail=str(item.get("detail", "")),
                severity=str(item.get("severity", "medium")).lower(),
            )
            findings.append(finding)
            self._emit_finding(finding)
        return findings

    async def analyze_memory_hygiene(self, run_id: str) -> List[dict]:
        """Разбирает карантин INBOX и предлагает, что продвинуть (I-2).

        Ничего не меняет сам: каждое предложение становится находкой с
        действием, которое сработает только после Apply человеком.
        """
        from backend.services import memory as memory_svc

        inbox = memory_svc.get_facts(layer=memory_svc.MemoryLayer.INBOX, limit=_INBOX_SAMPLE)
        if not inbox:
            logger.info("INBOX пуст — гигиена памяти не требуется")
            return []

        context = "\n".join(f"[{f.id}] ({f.source}) {f.content[:300]}" for f in inbox)
        raw = await self.llm.generate_response(
            _HYGIENE_PROMPT.format(context=context), kind=budget.BACKGROUND, json_mode=True
        )
        parsed = _parse_json(raw)
        known = {f.id for f in inbox}

        findings = []
        for item in parsed.get("promote", [])[:10]:
            fact_id = str(item.get("fact_id", "")).strip()
            if fact_id not in known:
                continue
            finding = dream_store.add_finding(
                run_id=run_id,
                dimension="Memory Hygiene",
                title=f"Продвинуть факт {fact_id} в OPERATIONAL",
                detail=str(item.get("reason", "")),
                severity="low",
                action={
                    "type": "promote_fact",
                    "fact_id": fact_id,
                    "to_layer": memory_svc.MemoryLayer.OPERATIONAL.value,
                },
            )
            findings.append(finding)
            self._emit_finding(finding)

        noise = [i for i in parsed.get("noise", []) if str(i.get("fact_id", "")) in known]
        if noise:
            finding = dream_store.add_finding(
                run_id=run_id,
                dimension="Memory Hygiene",
                title=f"В INBOX накопилось {len(noise)} записей без ценности",
                detail="Шум диалога. Автоматика ничего не удаляет — решение за человеком.",
                severity="low",
            )
            findings.append(finding)
            self._emit_finding(finding)

        return findings

    @staticmethod
    def _emit_finding(finding: dict) -> None:
        eventbus.emit(
            eventbus.DREAM_FINDING,
            {
                "finding_id": finding["finding_id"],
                "dimension": finding["dimension"],
                "severity": finding["severity"],
                "title": finding["title"],
            },
            source=eventbus.SOURCE_DREAM,
        )

    async def run_full_analysis(self) -> Dict[str, Any]:
        """Полный ночной прогон. Возвращает сводку по прогону."""
        run_id = dream_store.new_run_id()
        spent_before = budget.spent_today()
        logger.info("Dream Cadence: начат прогон %s", run_id)

        all_findings: List[dict] = []
        for dimension in self.ANALYSIS_DIMENSIONS:
            try:
                all_findings.extend(await self.analyze_dimension(run_id, dimension))
            except budget.BudgetExceeded as e:
                logger.warning("Прогон остановлен бюджетом на '%s': %s", dimension, e)
                break
            except Exception:
                logger.exception("Измерение '%s' упало", dimension)

        cost = budget.spent_today() - spent_before
        eventbus.emit(
            eventbus.DREAM_COMPLETED,
            {"run_id": run_id, "findings_count": len(all_findings), "cost_usd": round(cost, 6)},
            source=eventbus.SOURCE_DREAM,
        )
        logger.info("Dream Cadence: прогон %s завершён, находок %d, $%.6f",
                    run_id, len(all_findings), cost)

        return {"run_id": run_id, "findings": all_findings, "cost_usd": cost}

    async def generate_morning_brief(self, run: Dict[str, Any]) -> str:
        """Бриф по находкам прогона. Пишется в кэш, /brief его читает (R-10)."""
        findings = run.get("findings", [])
        if not findings:
            brief = (
                f"Доброе утро. Ночной прогон {run['run_id']} прошёл без находок — "
                "система в порядке, вмешательство не требуется."
            )
        else:
            listing = "\n".join(
                f"- [{f['severity']}] {f['dimension']}: {f['title']}" for f in findings
            )
            brief = await self.llm.generate_response(
                "Составь короткий утренний бриф (до 200 слов) по находкам ночного "
                "анализа. Без воды, только по делу, с конкретными действиями.\n\n"
                f"Находки:\n{listing}",
                kind=budget.BACKGROUND,
            )

        dream_store.save_brief(
            run_id=run["run_id"],
            brief=brief,
            cost_usd=run.get("cost_usd", 0.0),
            findings_count=len(findings),
        )
        return brief

    async def send_brief_to_telegram(self, brief: str):
        """Send morning brief to Telegram (if configured)"""
        try:
            from telegram import Bot

            bot_token = settings.telegram_bot_token
            chat_id = settings.telegram_allowed_user_id

            if bot_token and chat_id:
                bot = Bot(token=bot_token)
                await bot.send_message(chat_id=chat_id, text=brief)
                logger.info("Утренний бриф отправлен в Telegram")
            else:
                logger.warning("Telegram не настроен, бриф сохранён в файл")
                self.save_brief_to_file(brief)
        except Exception as e:
            logger.error(f"Не удалось отправить бриф: {e}")
            self.save_brief_to_file(brief)

    def save_brief_to_file(self, brief: str):
        """Save brief to file as fallback"""
        artifacts_path = os.getenv("HERMES_ARTIFACTS_PATH", "./artifacts")
        os.makedirs(artifacts_path, exist_ok=True)

        filename = f"{artifacts_path}/brief_{datetime.now().strftime('%Y-%m-%d')}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# Утренний бриф\n")
            f.write(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(brief)

        logger.info(f"Бриф сохранён в {filename}")

    async def nightly_job(self):
        """Ночная работа: анализ, бриф, отправка."""
        try:
            run = await self.run_full_analysis()
            brief = await self.generate_morning_brief(run)
            await self.send_brief_to_telegram(brief)
        except budget.BudgetExceeded as e:
            logger.warning("Ночной прогон отменён бюджетом: %s", e)
        except Exception:
            logger.exception("Ночной прогон упал")

    async def wallet_job(self):
        """Ежедневная проверка подписок: обновить балансы и предупредить."""
        from backend.services import wallet

        try:
            await wallet.refresh_balances()
            summary = wallet.summary()
        except Exception:
            logger.exception("Проверка подписок не удалась")
            return

        alerts = []
        for s in summary["due_soon"]:
            days = s["days_left"]
            when = "сегодня" if days == 0 else (
                f"через {days} дн." if days > 0 else f"просрочено на {-days} дн."
            )
            cancel = f"\nОтменить: {s['cancel_url']}" if s.get("cancel_url") else ""
            alerts.append(f"💳 {s['name']}: списание {when}, ${s['cost']}{cancel}")
        for s in summary["low_balance"]:
            alerts.append(f"🪫 {s['name']}: остаток ${s['balance']} — пора пополнить")

        if not alerts:
            return

        text = "Напоминание по сервисам:\n\n" + "\n\n".join(alerts)
        eventbus.emit(
            "wallet.alert",
            {"count": len(alerts), "services": [s["name"] for s in summary["due_soon"]]},
            source=eventbus.SOURCE_SYSTEM,
        )
        await self.send_brief_to_telegram(text)

    def start(self):
        """Start the scheduler"""
        if self.scheduler.running:
            return
        self.scheduler.add_job(
            self.nightly_job,
            trigger=self.trigger,
            id="dream_cadence",
            name="Night Analytics",
            replace_existing=True,
        )
        # Подписки проверяем утром: напоминание должно прийти до списания,
        # а не ночью, когда его никто не прочитает
        self.scheduler.add_job(
            self.wallet_job,
            trigger=CronTrigger(hour=9, minute=0),
            id="wallet_check",
            name="Subscription Watch",
            replace_existing=True,
        )

        # Автопилот: джоба ставится всегда, но каждый тик сам проверяет
        # выключатель. Так его можно включить без перезапуска приложения.
        from . import autopilot

        self.scheduler.add_job(
            autopilot.tick,
            trigger=IntervalTrigger(minutes=settings.jarvis_interval_min),
            id="jarvis_autopilot",
            name="Jarvis Autopilot",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            "Dream Cadence: %s | подписки: 9:00 | автопилот: %s (каждые %d мин)",
            self.cron_schedule,
            "включён" if autopilot.is_enabled() else "выключен",
            settings.jarvis_interval_min,
        )

    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Dream Cadence остановлен")


# Singleton instance
dream_cadence = DreamCadence()


def start_dream_cadence():
    """Start Dream Cadence scheduler"""
    dream_cadence.start()


def stop_dream_cadence():
    """Stop Dream Cadence scheduler"""
    dream_cadence.stop()
