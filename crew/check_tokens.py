"""Проверка токенов без их разглашения.

Договорённость с фаундером: секреты живут только в `.env`, он вписывает их
сам, и они не попадают ни в переписку, ни в вывод команд. Поэтому здесь
нельзя просто напечатать значение — даже начало значения.

Скрипт отвечает на три вопроса и ни на один сверх того: заполнена ли
переменная, похоже ли содержимое на настоящий токен Telegram, и запустится
ли команда. Само значение не покидает этот процесс.

Запуск:  python -m crew.check_tokens
"""
from __future__ import annotations

import os
import re

from . import config

# Токен Telegram выглядит как `<числовой id бота>:<35 символов>`.
# Проверяем форму, а не содержимое — этого достаточно, чтобы поймать
# обрезанный при вставке токен или случайно вставленный не тот текст.
TOKEN_SHAPE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,50}$")


def inspect(value: str) -> str:
    if not value:
        return "— пусто"
    if TOKEN_SHAPE.match(value):
        return f"✅ заполнен, форма верная ({len(value)} символов)"
    if ":" not in value:
        return "⚠️ заполнен, но нет двоеточия — это не токен Telegram"
    return f"⚠️ заполнен, но форма странная ({len(value)} символов) — проверь, не обрезался ли при вставке"


def main() -> int:
    print("Токены ботов (значения не показываются):\n")

    filled = 0
    for role in config.ROLES:
        value = os.getenv(role.env_token, "").strip()
        if value:
            filled += 1
        print(f"  {role.title:16} {role.env_token:26} {inspect(value)}")

    shared = os.getenv("CREW_TOKEN_ALL", "").strip()
    print(f"\n  {'Общий бот':16} {'CREW_TOKEN_ALL':26} {inspect(shared)}")

    allowed = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
    ids = [chunk for chunk in allowed.replace(";", ",").split(",") if chunk.strip().isdigit()]
    print(f"\n  Кому разрешено писать: {len(ids)} id" if ids else "\n  ⛔ TELEGRAM_ALLOWED_USER_ID пуст — бот не запустится")

    print()
    if filled:
        print(f"Готово к запуску: {filled} ролей на отдельных ботах.")
    elif shared:
        print("Готово к запуску: один бот на всю команду, роль переключается /role.")
    else:
        print("Ни одного токена нет. Впиши хотя бы CREW_TOKEN_ALL в .env.")
        return 1

    if filled and shared:
        print("Замечание: заданы и отдельные токены, и общий. Общий будет "
              "проигнорирован — отдельные важнее.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
