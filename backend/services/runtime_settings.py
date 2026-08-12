"""Переключатели, которые живут между перезапусками.

Раньше автопилот включался только переменной среды `NEXUS_AUTOPILOT`, а её
читают один раз при старте: чтобы передумать, нужно править файл и
перезапускать бэкенд. Кнопки в интерфейсе так не сделать.

Здесь хранятся переопределения, которые ставит человек из интерфейса. Они
сильнее переменных среды — потому что переменная это позиция по умолчанию,
а нажатие кнопки это сегодняшнее решение.
"""
from ..core.config import DATA_DIR, ensure_data_dir
from ..core.jsonio import read_json, write_json

SETTINGS_FILE = DATA_DIR / "runtime_settings.json"


def _load() -> dict:
    ensure_data_dir()
    data = read_json(SETTINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def _save(data: dict):
    ensure_data_dir()
    write_json(SETTINGS_FILE, data)


def get(key: str, default=None):
    """Значение переопределения. default — когда человек ничего не решал."""
    return _load().get(key, default)


def set_value(key: str, value):
    data = _load()
    data[key] = value
    _save(data)
    return value


def clear(key: str) -> bool:
    """Убирает переопределение — снова действует переменная среды."""
    data = _load()
    if key not in data:
        return False
    del data[key]
    _save(data)
    return True


def all_overrides() -> dict:
    return _load()


# === Конкретные переключатели ===

AUTOPILOT = "autopilot"
SKILL_DISABLED_PREFIX = "skill_disabled:"


def autopilot_override() -> bool | None:
    """True/False — решение человека, None — не решал, действует .env."""
    value = get(AUTOPILOT)
    return value if isinstance(value, bool) else None


def set_autopilot(enabled: bool) -> bool:
    return set_value(AUTOPILOT, bool(enabled))


def is_skill_enabled(skill_id: str) -> bool:
    """Скиллы включены по умолчанию: выключение — осознанное действие."""
    return not get(f"{SKILL_DISABLED_PREFIX}{skill_id}", False)


def set_skill_enabled(skill_id: str, enabled: bool) -> bool:
    key = f"{SKILL_DISABLED_PREFIX}{skill_id}"
    if enabled:
        clear(key)
    else:
        set_value(key, True)
    return enabled


def disabled_skills() -> list[str]:
    return [
        k[len(SKILL_DISABLED_PREFIX):]
        for k, v in _load().items()
        if k.startswith(SKILL_DISABLED_PREFIX) and v
    ]
