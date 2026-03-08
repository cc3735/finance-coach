"""
tts_service.py — ElevenLabs TTS for Finance Coach.

WHY THIS EXISTS:
Finance Coach uses a warm, reassuring voice (ElevenLabs "Sarah") rather than
the assertive Sports Vision voice. Financial coaching needs to feel supportive
not alarming — even budget threshold alerts should be delivered calmly so the
user doesn't feel judged.

VOICE SETTINGS:
  low urgency:    stability=0.85, slower, warm — routine updates
  medium urgency: stability=0.70 — budget threshold warnings
  high urgency:   stability=0.55 — over-budget alerts
"""

import asyncio
import hashlib
import os
from typing import Optional
from app.services.logger import get_logger

logger = get_logger(__name__)

FINANCE_VOICE_ID = os.getenv("ELEVENLABS_FINANCE_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

URGENCY_SETTINGS = {
    "low": {"stability": 0.85, "similarity_boost": 0.75, "style": 0.0, "speed": 0.95},
    "medium": {"stability": 0.70, "similarity_boost": 0.80, "style": 0.1, "speed": 1.0},
    "high": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.3, "speed": 1.05},
}


class FinanceTTSService:
    """ElevenLabs TTS with a warm, reassuring voice preset for finance coaching."""

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._client = None

    async def synthesize(self, script: str, urgency: str = "low") -> Optional[str]:
        """Convert script to MP3 base64. Cached by content + urgency."""
        cache_key = hashlib.md5(f"{script}:{urgency}".encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        client = self._get_client()
        if client is None:
            return None

        settings = URGENCY_SETTINGS.get(urgency, URGENCY_SETTINGS["low"])

        try:
            import base64

            audio = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.text_to_speech.convert(
                    voice_id=FINANCE_VOICE_ID,
                    text=script,
                    model_id="eleven_turbo_v2",
                    voice_settings={
                        "stability": settings["stability"],
                        "similarity_boost": settings["similarity_boost"],
                        "style": settings["style"],
                        "use_speaker_boost": True,
                    },
                    output_format="mp3_22050_32",
                )
            )

            audio_bytes = b"".join(chunk for chunk in audio)
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

            if len(self._cache) < 200:
                self._cache[cache_key] = audio_b64

            return audio_b64

        except Exception as e:
            logger.error("finance_tts_failed", error=str(e))
            return None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from elevenlabs.client import ElevenLabs
            key = os.getenv("ELEVENLABS_API_KEY")
            if key:
                self._client = ElevenLabs(api_key=key)
        except ImportError:
            logger.error("elevenlabs_not_installed")
        return self._client
