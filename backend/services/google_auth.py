"""Единый вход в Google для почты и календаря.

Раньше это были две несогласованные истории: почта искала
`credentials.json` в корне проекта, календарь — `google_credentials.json` в
папке данных, и токены хранились раздельно. Один и тот же файл от Google
пришлось бы класть дважды, а вход проходить два раза.

Здесь один файл доступа, один вход и один токен на оба сервиса. Старые
места читаются тоже — чтобы у того, кто уже разложил файлы по-старому,
ничего не сломалось.
"""
import logging
from pathlib import Path

from ..core.config import DATA_DIR, ensure_data_dir

logger = logging.getLogger(__name__)

# Куда кладём файл доступа. Первый путь — основной, остальные оставлены
# ради совместимости со старой раскладкой
CREDENTIALS_PATHS = (
    DATA_DIR / "google_credentials.json",
    Path("credentials.json"),
    DATA_DIR / "credentials.json",
)

TOKEN_FILE = DATA_DIR / "google_token.json"

# Разрешения просим минимальные и осознанно: календарь — читать и создавать
# события, почта — читать и готовить черновики. Отправки писем нет и в
# правах: система физически не сможет отправить письмо за человека.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


class GoogleNotConnected(RuntimeError):
    """Нет файла доступа или не пройден вход. Причина — в тексте."""


def credentials_path() -> Path | None:
    """Где лежит файл доступа. None — если его нет нигде."""
    for path in CREDENTIALS_PATHS:
        if path.exists():
            return path
    return None


def has_credentials() -> bool:
    return credentials_path() is not None


def has_token() -> bool:
    return TOKEN_FILE.exists()


def status() -> dict:
    """Что готово, чего не хватает и что делать дальше."""
    creds = credentials_path()
    if not creds:
        return {
            "ready": False,
            "step": "нет файла доступа",
            "detail": (
                "Нужен OAuth-файл из Google Cloud Console (тип «Desktop app»). "
                f"Положить сюда: {CREDENTIALS_PATHS[0]}"
            ),
        }
    if not has_token():
        return {
            "ready": False,
            "step": "не пройден вход",
            "detail": (
                "Файл доступа найден. Осталось войти в аккаунт: "
                "python -m cli.main google-auth"
            ),
            "credentials": str(creds),
        }
    return {
        "ready": True,
        "step": "подключено",
        "detail": "почта и календарь работают от одного входа",
        "credentials": str(creds),
        "token": str(TOKEN_FILE),
    }


def load_credentials():
    """Готовые учётные данные или понятная ошибка.

    Протухший токен обновляем сами: человек не должен входить заново каждый
    час только потому, что Google отдаёт короткий доступ.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise GoogleNotConnected(
            "Не установлены библиотеки Google: pip install google-auth google-auth-oauthlib "
            "google-api-python-client"
        ) from e

    if not TOKEN_FILE.exists():
        raise GoogleNotConnected(
            "Вход в Google не пройден. Выполните: python -m cli.main google-auth"
        )

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Токен Google обновлён")

    if not creds or not creds.valid:
        raise GoogleNotConnected(
            "Токен Google недействителен. Пройдите вход заново: python -m cli.main google-auth"
        )
    return creds


def authorize() -> dict:
    """Проводит вход в Google и сохраняет токен.

    Открывает браузер: подтверждать доступ должен человек, своими руками.
    Система только сохраняет результат.
    """
    creds_path = credentials_path()
    if not creds_path:
        raise GoogleNotConnected(
            "Нет файла доступа. Скачайте OAuth-файл (Desktop app) из Google Cloud Console "
            f"и положите сюда: {CREDENTIALS_PATHS[0]}"
        )

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise GoogleNotConnected(
            "Не установлен google-auth-oauthlib: pip install google-auth-oauthlib"
        ) from e

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)

    ensure_data_dir()
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    logger.info("Вход в Google пройден, токен сохранён в %s", TOKEN_FILE)
    return {"token": str(TOKEN_FILE), "credentials": str(creds_path)}
