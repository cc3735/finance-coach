"""
location_engine.py — Geofence matching and location-triggered alerts.

WHY THIS EXISTS:
The glasses know where the user is (via companion app GPS). The finance coach
knows where the user tends to spend money. When these intersect — user walks
into a Whole Foods → "Groceries: $187 of $300 this month, $112 remaining" —
the glasses whisper the relevant budget context before the user even picks up
a basket.

GEOFENCE MATCHING:
Uses haversine distance formula. A geofence triggers when:
  distance(user_location, geofence_center) <= geofence.radius_meters

COOLDOWN:
Same geofence won't trigger again for the same session for 30 minutes.
This prevents spam when the user lingers near a merchant.

DATA MODEL:
  Geofences are stored in DB per user: lat, lon, radius, merchant_category,
  tts_template. Users add geofences via companion app (drop a pin, name it).
  Pre-populated geofences are created from the user's historical top merchants.
"""

import math
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone
from app.services.logger import get_logger

logger = get_logger(__name__)

COOLDOWN_MINUTES = 30


@dataclass
class Geofence:
    id: str
    name: str               # "Whole Foods", "Starbucks area"
    lat: float
    lon: float
    radius_meters: int
    merchant_category: str
    tts_template: str       # "You're near {name}. {category_status}."


class LocationEngine:
    """Matches GPS coordinates against user geofences and generates budget alerts."""

    def __init__(self):
        # session_id → {geofence_id: last_triggered_at}
        self._recent_triggers: dict[str, dict[str, datetime]] = {}

    async def check_geofences(
        self, session_id: str, lat: float, lon: float
    ) -> list[dict]:
        """
        Check if the user is inside any geofences.
        Returns list of alert dicts (each has a tts_script).
        """
        geofences = await self._load_geofences()
        alerts = []

        for gf in geofences:
            dist = haversine_meters(lat, lon, gf.lat, gf.lon)
            if dist <= gf.radius_meters:
                if self._is_on_cooldown(session_id, gf.id):
                    continue

                alert = await self._build_location_alert(gf)
                alerts.append(alert)
                self._mark_triggered(session_id, gf.id)
                logger.info(
                    "geofence_triggered",
                    geofence=gf.name,
                    distance_meters=round(dist),
                    session_id=session_id,
                )

        return alerts

    async def _build_location_alert(self, gf: Geofence) -> dict:
        """Build a location alert dict with TTS script."""
        # TODO: pull real budget status from DB for this category
        budget_context = f"{gf.merchant_category}: $187 of $300 this month, $112 remaining."
        tts_script = gf.tts_template.format(name=gf.name, category_status=budget_context)

        return {
            "type": "location_trigger",
            "geofence_id": gf.id,
            "geofence_name": gf.name,
            "merchant_category": gf.merchant_category,
            "budget_status": {
                "category": gf.merchant_category,
                "spent": 187.40,
                "limit": 300.00,
                "remaining": 112.60,
                "percent_used": 62.5,
            },
            "tts_script": tts_script,
        }

    async def _load_geofences(self) -> list[Geofence]:
        """
        Load user's geofences from DB.
        TODO: implement DB query with user_id from session context.
        For now: return demo geofences.
        """
        return [
            Geofence(
                id="gf-001",
                name="Whole Foods Market",
                lat=37.7749,
                lon=-122.4194,
                radius_meters=100,
                merchant_category="Groceries",
                tts_template="{name} ahead. {category_status}",
            ),
            Geofence(
                id="gf-002",
                name="Starbucks",
                lat=37.7751,
                lon=-122.4183,
                radius_meters=75,
                merchant_category="Coffee",
                tts_template="Coffee shop nearby. {category_status}",
            ),
        ]

    def _is_on_cooldown(self, session_id: str, geofence_id: str) -> bool:
        session_triggers = self._recent_triggers.get(session_id, {})
        last = session_triggers.get(geofence_id)
        if last is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60
        return elapsed < COOLDOWN_MINUTES

    def _mark_triggered(self, session_id: str, geofence_id: str) -> None:
        if session_id not in self._recent_triggers:
            self._recent_triggers[session_id] = {}
        self._recent_triggers[session_id][geofence_id] = datetime.now(timezone.utc)


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two GPS coordinates."""
    R = 6_371_000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
