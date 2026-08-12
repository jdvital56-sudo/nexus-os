"""Google Calendar integration — read events, create from tasks.

Uses Google Calendar API v3. Requires OAuth2 credentials.
Falls back to mock mode if credentials not configured.
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from ..core.config import DATA_DIR, ensure_data_dir
from ..core.jsonio import read_json, write_json

CREDENTIALS_FILE = DATA_DIR / "google_credentials.json"
TOKEN_FILE = DATA_DIR / "google_token.json"

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """Готов ли календарь: вход в Google общий для почты и календаря."""
    from . import google_auth

    return google_auth.has_credentials() or google_auth.has_token()


def get_upcoming_events(days: int = 7, max_results: int = 20) -> list[dict]:
    """Get upcoming calendar events.

    Returns list of event dicts with: id, summary, start, end, description, attendees.
    Falls back to reading from local cache if API not available.
    """
    if not is_configured():
        return _read_cached_events()

    try:
        return _fetch_from_api(days, max_results)
    except Exception as e:
        # Fallback to cache
        return _read_cached_events()


def _fetch_from_api(days: int, max_results: int) -> list[dict]:
    """Fetch events from Google Calendar API."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("google-api-python-client not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

    creds = _get_credentials()
    if not creds:
        raise RuntimeError("No valid Google credentials")

    service = build("calendar", "v3", credentials=creds)

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days)).isoformat() + "Z"

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    return [_format_event(e) for e in events]


def _format_event(event: dict) -> dict:
    """Format Google Calendar event to NEXSYS format."""
    start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
    end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date", ""))
    attendees = [a.get("email", "") for a in event.get("attendees", [])]

    return {
        "id": event.get("id", ""),
        "summary": event.get("summary", "(no title)"),
        "start": start,
        "end": end,
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "attendees": attendees,
        "status": event.get("status", "confirmed"),
        "html_link": event.get("htmlLink", ""),
    }


def _get_credentials():
    """Учётные данные из общего входа. None — если вход не пройден."""
    from . import google_auth

    try:
        return google_auth.load_credentials()
    except google_auth.GoogleNotConnected:
        return None


def _read_cached_events() -> list[dict]:
    """Read events from local cache (for offline/ mock mode)."""
    cache_file = DATA_DIR / "calendar_cache.json"
    if cache_file.exists():
        return read_json(cache_file, {})
    return []


def cache_events(events: list[dict]):
    """Cache events locally for offline access."""
    ensure_data_dir()
    cache_file = DATA_DIR / "calendar_cache.json"
    write_json(cache_file, events)


def create_event_from_task(task: dict, duration_minutes: int = 60) -> dict | None:
    """Create a Google Calendar event from a NEXSYS task.

    Returns created event or None if not configured.
    """
    if not is_configured():
        return None

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None

    creds = _get_credentials()
    if not creds:
        return None

    service = build("calendar", "v3", credentials=creds)

    now = datetime.utcnow()
    event_body = {
        "summary": f"[NEXSYS] {task.get('title', 'Task')}",
        "description": task.get("description", ""),
        "start": {
            "dateTime": now.isoformat() + "Z",
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": (now + timedelta(minutes=duration_minutes)).isoformat() + "Z",
            "timeZone": "UTC",
        },
    }

    created = service.events().insert(calendarId="primary", body=event_body).execute()
    return _format_event(created)


class CalendarNotConnected(RuntimeError):
    """Календарь не подключён. Причина — в тексте, а не «что-то пошло не так»."""


def create_event(
    summary: str,
    start: datetime,
    duration_minutes: int = 60,
    description: str = "",
) -> dict:
    """Ставит событие на заданное время.

    До этого система умела только `create_event_from_task`, а тот всегда
    ставил встречу «сейчас» — то есть сказать «поставь на четверг в 15:00»
    было невозможно в принципе.

    Время приходит местное: человек говорит «в 15:00», имея в виду свои
    часы, а не UTC. Отдаём Google местную зону явно.
    """
    if not summary or not summary.strip():
        raise ValueError("У события должно быть название")
    if not is_configured():
        raise CalendarNotConnected(
            "Google Calendar не подключён: нет файла доступа. "
            "Нужен google_credentials.json в папке данных."
        )

    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        raise CalendarNotConnected("Не установлен google-api-python-client") from e

    creds = _get_credentials()
    if not creds:
        raise CalendarNotConnected(
            "Файл доступа есть, но авторизация не пройдена: нужен вход в Google"
        )

    local_zone = datetime.now().astimezone().tzname() or "UTC"
    body = {
        "summary": summary.strip(),
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": local_zone},
        "end": {
            "dateTime": (start + timedelta(minutes=duration_minutes)).isoformat(),
            "timeZone": local_zone,
        },
    }

    service = build("calendar", "v3", credentials=creds)
    created = service.events().insert(calendarId="primary", body=body).execute()
    logger.info("Событие создано: %s на %s", summary, start.isoformat())
    return _format_event(created)


def sync_events_to_graph(events: list[dict]) -> dict:
    """Sync calendar events as graph nodes."""
    from . import graph as graph_svc
    from ..models.schemas import GraphNode, NodeType

    added = 0
    for event in events:
        node = GraphNode(
            id=f"cal:{event['id'][:20]}",
            label=event["summary"],
            node_type=NodeType.SESSION,
            metadata={
                "source": "google_calendar",
                "start": event.get("start", ""),
                "end": event.get("end", ""),
                "attendees": event.get("attendees", []),
                "location": event.get("location", ""),
            },
        )
        try:
            graph_svc.add_node(node)
            added += 1
        except Exception:
            pass  # already exists

    return {"events_synced": added, "total": len(events)}


def setup_instructions() -> str:
    """Return setup instructions for Google Calendar integration."""
    return """To connect Google Calendar:

1. Go to https://console.cloud.google.com/apis/credentials
2. Create OAuth 2.0 Client ID (Desktop app)
3. Download credentials.json
4. Place it at: ~/.nexsys/google_credentials.json
5. Run: nexsys calendar auth
6. Follow the browser flow to authorize

Required scopes:
- calendar.readonly
- calendar.events

Alternative: Use service account for server-to-server."""
