"""JSON-хранилища всегда UTF-8, старые файлы переезжают сами (I-8)."""
import json
import threading

import pytest

from backend.core.jsonio import lock, locked_update, read_json, write_json
from backend.services import memory as mem_svc
from backend.services.memory import MemoryLayer


def test_cyrillic_is_written_as_utf8(tmp_path):
    path = tmp_path / "data.json"
    write_json(path, {"текст": "Привет, мир"})

    # Именно UTF-8, а не системная кодировка Windows
    assert json.loads(path.read_text(encoding="utf-8"))["текст"] == "Привет, мир"


def test_cyrillic_is_not_escaped(tmp_path):
    path = tmp_path / "data.json"
    write_json(path, {"k": "Привет"})

    assert "Привет" in path.read_text(encoding="utf-8")
    assert "\\u041f" not in path.read_text(encoding="utf-8")


def test_legacy_cp1251_file_is_read_and_migrated(tmp_path):
    """Данные, записанные до исправления, не должны пропасть."""
    path = tmp_path / "legacy.json"
    path.write_bytes(json.dumps({"k": "Привет"}, ensure_ascii=False).encode("cp1251"))

    assert read_json(path) == {"k": "Привет"}
    # Файл переписан в UTF-8 — второе чтение уже без запасного пути
    assert path.read_text(encoding="utf-8")


def test_broken_file_falls_back_to_default(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{не json", encoding="utf-8")

    assert read_json(path, default=[]) == []


def test_missing_file_returns_default(tmp_path):
    assert read_json(tmp_path / "нет.json", default={"a": 1}) == {"a": 1}


def test_memory_file_survives_utf8_roundtrip():
    """Сквозная проверка: факт с кириллицей читается как UTF-8."""
    mem_svc.add_fact("Фаундер живёт в Одессе", layer=MemoryLayer.INBOX)

    raw = mem_svc.MEMORY_FILE.read_text(encoding="utf-8")
    assert "Одессе" in raw
    assert mem_svc.get_facts(layer=MemoryLayer.INBOX)[0].content == "Фаундер живёт в Одессе"


# --- Атомарность и межпроцессный лок (23.08.2026, по итогам аудита) ---


def test_write_does_not_leave_tmp_files_behind(tmp_path):
    path = tmp_path / "data.json"
    write_json(path, {"a": 1})

    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []
    assert read_json(path) == {"a": 1}


def test_write_replaces_atomically_not_appends(tmp_path):
    path = tmp_path / "data.json"
    write_json(path, {"a": 1})
    write_json(path, {"b": 2})

    # Не два JSON-объекта подряд в файле — второй полностью заменил первый
    assert read_json(path) == {"b": 2}


def test_corrupt_file_is_renamed_not_silently_discarded(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{не json", encoding="utf-8")

    result = read_json(path, default=[])

    assert result == []
    assert not path.exists()  # оригинал переехал, не остался как есть
    corrupted = list(tmp_path.glob("broken.json.corrupt-*"))
    assert len(corrupted) == 1
    assert corrupted[0].read_text(encoding="utf-8") == "{не json"


def test_locked_update_applies_mutation_and_persists(tmp_path):
    path = tmp_path / "list.json"
    write_json(path, [1, 2])

    result = locked_update(path, lambda data: data + [3], default=[])

    assert result == [1, 2, 3]
    assert read_json(path) == [1, 2, 3]


def test_locked_update_starts_from_default_when_file_missing(tmp_path):
    path = tmp_path / "new.json"

    result = locked_update(path, lambda data: data + ["первый"], default=[])

    assert result == ["первый"]


def test_locked_update_does_not_write_when_mutate_raises(tmp_path):
    path = tmp_path / "list.json"
    write_json(path, [1])

    def boom(data):
        raise ValueError("не сегодня")

    with pytest.raises(ValueError):
        locked_update(path, boom, default=[])

    assert read_json(path) == [1]  # файл не тронут


def test_locked_update_survives_concurrent_writers(tmp_path):
    """Не теоретическая гонка — ровно тот P0, что нашёл аудит: два
    писателя без лока теряли бы правки друг друга. С locked_update ни
    одна из 50 параллельных прибавок не должна потеряться."""
    path = tmp_path / "counter.json"
    write_json(path, {"n": 0})

    def bump(data):
        data["n"] += 1
        return data

    def worker():
        locked_update(path, bump, default={"n": 0})

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert read_json(path)["n"] == 50


def test_lock_is_reentrant_safe_for_sequential_calls(tmp_path):
    path = tmp_path / "seq.json"
    with lock(path):
        pass
    with lock(path):
        pass  # второй заход после освобождения первого не должен виснуть
