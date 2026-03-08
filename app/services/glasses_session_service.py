"""
glasses_session_service.py — Finance Coach glasses session lifecycle management.
"""

from typing import Optional
from datetime import datetime, timezone
from services.logger import get_logger

logger = get_logger(__name__)

# In-memory session store (replace with DB in production)
_sessions: dict[str, dict] = {}


class GlassesSessionService:
    def create_session(self, session_id: str, token: str, device_fingerprint: str) -> None:
        _sessions[session_id] = {
            "token": token,
            "device_fingerprint": device_fingerprint,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "active": True,
        }
        logger.info("finance_session_created", session_id=session_id)

    def end_session(self, session_id: str) -> None:
        if session_id in _sessions:
            _sessions[session_id]["active"] = False
            _sessions[session_id]["ended_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("finance_session_ended", session_id=session_id)

    def is_valid(self, session_id: str, token: str) -> bool:
        session = _sessions.get(session_id)
        return session is not None and session.get("token") == token and session.get("active", False)

    def get_active_sessions(self) -> list[str]:
        return [sid for sid, s in _sessions.items() if s.get("active", False)]
