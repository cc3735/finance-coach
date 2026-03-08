"""
glasses.py — Glasses-first API endpoints for Finance Coach.

WHY THIS IS THE PRIMARY MODULE:
The phone UI is secondary. Every feature in Finance Coach is designed to
work entirely through the glasses TTS interface. These endpoints are what
the companion app calls — all other routes exist to configure the data that
these endpoints surface.

WEBSOCKET PROTOCOL:
  Client → Server:
    LocationUpdate: { type, lat, lon, accuracy_meters }
    VoiceQuery:    { type, transcript, confidence, audio_base64 }
    GestureEvent:  { type, gesture }

  Server → Client:
    LocationTriggerAlert: budget context when entering a geofence
    TransactionAlert:     real-time Plaid transaction notification
    BudgetAlert:          category approaching or over limit
    MorningBriefing:      daily financial digest on glasses put-on
    CoachResponse:        GPT-4o answer to voice query
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import uuid
from datetime import datetime, timezone

from app.services.glasses_session_service import GlassesSessionService
from app.services.alert_engine import AlertEngine
from app.services.ai_coach_service import AICoachService
from app.services.tts_service import FinanceTTSService
from app.services.location_engine import LocationEngine
from app.services.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/glasses", tags=["Glasses Finance"])

# Active WebSocket sessions
_sessions: dict[str, WebSocket] = {}

# Service singletons (lazy)
_session_svc: Optional[GlassesSessionService] = None
_alert_engine: Optional[AlertEngine] = None
_coach: Optional[AICoachService] = None
_tts: Optional[FinanceTTSService] = None
_location: Optional[LocationEngine] = None


def get_session_svc():
    global _session_svc
    if _session_svc is None:
        _session_svc = GlassesSessionService()
    return _session_svc


def get_alert_engine():
    global _alert_engine
    if _alert_engine is None:
        _alert_engine = AlertEngine()
    return _alert_engine


def get_coach():
    global _coach
    if _coach is None:
        _coach = AICoachService()
    return _coach


def get_tts():
    global _tts
    if _tts is None:
        _tts = FinanceTTSService()
    return _tts


def get_location():
    global _location
    if _location is None:
        _location = LocationEngine()
    return _location


# =============================================================================
# SCHEMAS
# =============================================================================

class SessionStartRequest(BaseModel):
    device_fingerprint: str
    enable_location_tracking: bool = True


class SessionStartResponse(BaseModel):
    session_id: str
    session_token: str
    morning_briefing_audio: Optional[str] = None   # Base64 MP3 if before cutoff hour
    message: str


class SessionEndRequest(BaseModel):
    session_id: str
    session_token: str
    reason: Optional[str] = "normal"


class VoiceQueryRequest(BaseModel):
    session_id: str
    stt_transcript: str
    confidence: float
    audio_base64: Optional[str] = None


class VoiceQueryResponse(BaseModel):
    response_text: str
    tts_audio_base64: Optional[str]
    data: dict = {}


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/session/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """
    Start a glasses session. Called when glasses are put on.

    If the current time is before the morning briefing cutoff hour (10am),
    a pre-synthesized morning briefing is included in the response.
    The companion app plays this immediately through the glasses speakers.
    """
    session_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    now = datetime.now()

    get_session_svc().create_session(session_id, session_token, request.device_fingerprint)

    morning_audio = None
    if now.hour < 10:
        coach = get_coach()
        tts = get_tts()
        briefing_text = await coach.generate_morning_briefing(session_id)
        morning_audio = await tts.synthesize(briefing_text, urgency="low")
        logger.info("morning_briefing_generated", session_id=session_id, hour=now.hour)

    return SessionStartResponse(
        session_id=session_id,
        session_token=session_token,
        morning_briefing_audio=morning_audio,
        message="Session started." + (" Morning briefing attached." if morning_audio else ""),
    )


@router.websocket("/session/{session_id}/stream")
async def glasses_stream(session_id: str, websocket: WebSocket):
    """
    Bidirectional WebSocket for the glasses finance session.

    Client sends location updates (every 60s or on significant move) and
    voice queries. Server pushes location triggers, transaction alerts, and
    budget alerts.
    """
    await websocket.accept()
    _sessions[session_id] = websocket

    location_engine = get_location()
    alert_engine = get_alert_engine()
    coach = get_coach()
    tts = get_tts()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "location_update":
                lat = float(msg.get("lat", 0))
                lon = float(msg.get("lon", 0))

                # Check geofences
                triggered = await location_engine.check_geofences(session_id, lat, lon)
                for alert in triggered:
                    audio = await tts.synthesize(alert["tts_script"], urgency="low")
                    await websocket.send_json({**alert, "tts_audio_base64": audio})

            elif msg_type == "voice_query":
                transcript = msg.get("transcript", "")
                confidence = float(msg.get("confidence", 0))

                if confidence < 0.80:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Voice confidence too low. Please repeat.",
                    })
                    continue

                response = await coach.answer_voice_query(session_id, transcript)
                audio = await tts.synthesize(response["tts_script"], urgency="low")

                await websocket.send_json({
                    "type": "coach_response",
                    "query": transcript,
                    "tts_script": response["tts_script"],
                    "tts_audio_base64": audio,
                    "insight": response.get("insight"),
                })

            elif msg_type == "gesture":
                gesture = msg.get("gesture")
                # Double-tap → budget summary; nod → dismiss
                if gesture == "double_tap":
                    summary = await coach.get_budget_summary(session_id)
                    audio = await tts.synthesize(summary, urgency="low")
                    await websocket.send_json({
                        "type": "budget_summary",
                        "tts_script": summary,
                        "tts_audio_base64": audio,
                    })

    except WebSocketDisconnect:
        _sessions.pop(session_id, None)
        logger.info("glasses_finance_ws_disconnected", session_id=session_id)
    except Exception as e:
        logger.error("glasses_finance_ws_error", session_id=session_id, error=str(e))
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


@router.post("/session/{session_id}/end")
async def end_session(session_id: str, request: SessionEndRequest):
    """End a glasses session. Returns a daily spend recap TTS."""
    coach = get_coach()
    tts = get_tts()

    recap_text = await coach.generate_daily_recap(session_id)
    recap_audio = await tts.synthesize(recap_text, urgency="low")

    _sessions.pop(session_id, None)
    get_session_svc().end_session(session_id)

    return {
        "session_id": session_id,
        "session_summary": recap_text,
        "tts_audio_base64": recap_audio,
    }


@router.post("/voice-query", response_model=VoiceQueryResponse)
async def voice_query(request: VoiceQueryRequest):
    """
    Process a voice query from the glasses. Non-WebSocket fallback.
    For HTTP-based environments or testing.
    """
    if request.confidence < 0.80:
        raise HTTPException(status_code=422, detail=f"STT confidence {request.confidence} too low")

    coach = get_coach()
    tts = get_tts()

    response = await coach.answer_voice_query(request.session_id, request.stt_transcript)
    audio = await tts.synthesize(response["tts_script"], urgency="low")

    return VoiceQueryResponse(
        response_text=response["tts_script"],
        tts_audio_base64=audio,
        data=response.get("data", {}),
    )


@router.get("/briefing")
async def get_briefing(session_id: str, briefing_type: str = "morning"):
    """On-demand financial briefing (morning | evening | on_demand)."""
    coach = get_coach()
    tts = get_tts()

    text = await coach.generate_briefing(session_id, briefing_type)
    audio = await tts.synthesize(text, urgency="low")

    return {
        "type": briefing_type,
        "tts_script": text,
        "tts_audio_base64": audio,
    }


# =============================================================================
# BROADCAST (called by Plaid webhook handler)
# =============================================================================

async def broadcast_transaction_alert(session_id: str, alert: dict):
    """
    Push a Plaid transaction alert to a connected glasses session.
    Called by the Plaid webhook handler when a transaction posts.
    """
    ws = _sessions.get(session_id)
    if ws:
        try:
            await ws.send_json(alert)
        except Exception as e:
            logger.warning("broadcast_failed", session_id=session_id, error=str(e))
