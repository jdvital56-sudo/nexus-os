"""Gmail: только черновики. Отправки здесь нет как метода (I-7).

Это не настройка и не флаг, который можно случайно переключить: в модуле
физически отсутствует код, способный отправить письмо. Система готовит
черновик, человек открывает Gmail и жмёт «Отправить» сам.

Честная оговорка про права. У Google нет OAuth-скоупа «только черновики»:
gmail.compose разрешает и создание черновиков, и отправку. То есть на
уровне токена право отправить существует — но воспользоваться им наш код
не может, потому что такого вызова в нём нет. Именно так это и описано в
хартии: минимальные привилегии по построению, а не по настройке.
"""
import base64
import logging
import os
from email.message import EmailMessage
from typing import Any

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "gmail_token.json"

# Минимум, которого хватает для черновиков и поиска по почте
SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailNotConfigured(RuntimeError):
    """Нет credentials.json — интеграция выключена."""


class GmailClient:
    """Клиент Gmail без единого метода отправки."""

    def __init__(self):
        self.service = None

    def is_configured(self) -> bool:
        """Вход в Google общий с календарём — файл кладётся один раз."""
        from . import google_auth

        return google_auth.has_credentials() or google_auth.has_token()

    def _connect(self):
        if self.service is not None:
            return self.service

        if not self.is_configured():
            raise GmailNotConfigured(
                f"Gmail не подключён: положите {CREDENTIALS_FILE} из Google Cloud "
                "в корень проекта"
            )

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)
        return self.service

    def create_draft(
        self, to: str, subject: str, body: str, cc: str = "", reply_to: str = ""
    ) -> dict[str, Any]:
        """Создать черновик. Письмо остаётся в Gmail неотправленным."""
        if not to or not to.strip():
            raise ValueError("Нужен адрес получателя")
        if not subject or not subject.strip():
            raise ValueError("Нужна тема письма")

        service = self._connect()

        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        if cc:
            message["Cc"] = cc
        if reply_to:
            message["In-Reply-To"] = reply_to
        message.set_content(body)

        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": encoded}})
            .execute()
        )

        logger.info("Черновик создан: %s -> %s", draft.get("id"), to)
        return {
            "draft_id": draft.get("id"),
            "to": to,
            "subject": subject,
            "status": "draft",
            "note": "Письмо НЕ отправлено. Откройте Gmail и отправьте сами.",
        }

    def list_drafts(self, limit: int = 10) -> list[dict[str, Any]]:
        """Показать неотправленные черновики."""
        service = self._connect()
        response = (
            service.users().drafts().list(userId="me", maxResults=limit).execute()
        )

        drafts = []
        for item in response.get("drafts", []):
            detail = (
                service.users()
                .drafts()
                .get(userId="me", id=item["id"], format="metadata")
                .execute()
            )
            headers = detail.get("message", {}).get("payload", {}).get("headers", [])
            fields = {h["name"].lower(): h["value"] for h in headers}
            drafts.append({
                "draft_id": item["id"],
                "to": fields.get("to", ""),
                "subject": fields.get("subject", "(без темы)"),
            })
        return drafts

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Поиск по почте — только чтение заголовков."""
        service = self._connect()
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=limit)
            .execute()
        )

        results = []
        for item in response.get("messages", []):
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=item["id"], format="metadata")
                .execute()
            )
            headers = detail.get("payload", {}).get("headers", [])
            fields = {h["name"].lower(): h["value"] for h in headers}
            results.append({
                "message_id": item["id"],
                "from": fields.get("from", ""),
                "subject": fields.get("subject", "(без темы)"),
                "date": fields.get("date", ""),
                "snippet": detail.get("snippet", "")[:200],
            })
        return results


gmail_client = GmailClient()
