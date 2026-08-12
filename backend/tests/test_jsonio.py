"""JSON-хранилища всегда UTF-8, старые файлы переезжают сами (I-8)."""
import json

from backend.core.jsonio import read_json, write_json
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
