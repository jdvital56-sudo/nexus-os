"""Короткая память диалога: нить последних реплик."""
from datetime import datetime, timedelta

from backend.services import dialog_history as history


def test_turn_is_stored_and_rendered():
    history.append_turn("telegram", "42", "привет", "здравствуй", "Orpheus")

    block = history.render("telegram", "42")
    assert "Пользователь: привет" in block
    assert "Orpheus: здравствуй" in block


def test_empty_history_renders_nothing():
    assert history.render("telegram", "42") == ""
    assert history.recent("telegram", "42") == []


def test_order_is_chronological_with_fresh_at_the_bottom():
    history.append_turn("telegram", "42", "первый вопрос", "первый ответ")
    history.append_turn("telegram", "42", "второй вопрос", "второй ответ")

    block = history.render("telegram", "42")
    assert block.index("первый вопрос") < block.index("второй вопрос")


def test_window_keeps_only_last_turns():
    for i in range(20):
        history.append_turn("telegram", "42", f"вопрос {i}", f"ответ {i}")

    turns = history.recent("telegram", "42")
    assert len(turns) == history.MAX_TURNS
    assert turns[-1]["text"] == "ответ 19"
    # Старое действительно выброшено, а не просто скрыто при выдаче
    assert "вопрос 0" not in history.render("telegram", "42")


def test_long_message_is_clipped():
    history.append_turn("telegram", "42", "я" * 5000, "ок")

    stored = history.recent("telegram", "42")[0]["text"]
    assert len(stored) <= history.MAX_CHARS + 1  # +1 на многоточие
    assert stored.endswith("…")


def test_users_do_not_see_each_other():
    history.append_turn("telegram", "42", "мой секрет", "принято")

    assert history.render("telegram", "77") == ""
    assert history.render("web", "42") == ""


def test_old_conversation_is_not_resurrected():
    """Вчерашняя переписка — уже другой разговор, в промпт не идёт."""
    history.append_turn("telegram", "42", "вчерашний вопрос", "вчерашний ответ")

    stale = datetime.utcnow() - timedelta(hours=history.SESSION_GAP_HOURS + 1)
    _shift_timestamps("telegram:42", stale.isoformat())

    assert history.recent("telegram", "42") == []
    assert history.render("telegram", "42") == ""


def test_broken_timestamp_keeps_the_thread():
    """Битая дата не должна молча стирать контекст."""
    history.append_turn("telegram", "42", "вопрос", "ответ")
    _shift_timestamps("telegram:42", "не дата")

    assert history.render("telegram", "42") != ""


def test_clear_forgets_the_thread():
    history.append_turn("telegram", "42", "вопрос", "ответ")

    removed = history.clear("telegram", "42")

    assert removed == 2
    assert history.render("telegram", "42") == ""
    assert history.clear("telegram", "42") == 0


def test_history_survives_restart():
    """Файл, а не память процесса: перезапуск бота не рвёт нить."""
    history.append_turn("telegram", "42", "до перезапуска", "принято")

    assert "до перезапуска" in history.render("telegram", "42")
    assert history.HISTORY_FILE.exists()


def _shift_timestamps(key: str, value: str) -> None:
    from backend.core.jsonio import read_json, write_json

    data = read_json(history.HISTORY_FILE, {})
    for entry in data[key]:
        entry["at"] = value
    write_json(history.HISTORY_FILE, data)
