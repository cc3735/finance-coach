"""
config.py — Finance Coach application settings.

All secrets loaded from environment variables. Never hardcode.
Copy env.example → .env and fill in values.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8003
    environment: str = "development"

    # Database (Supabase PostgreSQL)
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/finance_coach"
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None

    # Plaid
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"  # sandbox | development | production

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_finance_voice_id: str = "EXAVITQu4vr4xnSDxMaL"  # "Sarah" — warm, reassuring

    # Auth
    api_key_header: str = "X-API-Key"
    master_api_key: str = "dev-finance-key"

    # Feature flags
    enable_location_tracking: bool = True
    morning_briefing_cutoff_hour: int = 10   # Morning briefing only before 10am
    geofence_radius_meters: int = 100

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
