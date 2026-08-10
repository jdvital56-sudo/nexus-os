"""Simple local auth (loopback token)."""
import json
import secrets
from pathlib import Path
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import AUTH_FILE, ensure_data_dir

security = HTTPBearer(auto_error=False)


def _load_token() -> str | None:
    if AUTH_FILE.exists():
        data = json.loads(AUTH_FILE.read_text())
        return data.get("token")
    return None


def init_auth() -> str:
    """Create or return existing local token."""
    ensure_data_dir()
    existing = _load_token()
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    AUTH_FILE.write_text(json.dumps({"token": token}, indent=2))
    return token


def get_token_dep():
    """FastAPI dependency — validates bearer token."""
    async def _verify(creds: HTTPAuthorizationCredentials | None = Depends(security)):
        token = _load_token()
        if not token:
            return True  # no auth configured = open
        if not creds or creds.credentials != token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return True
    return _verify
