"""Application configuration and settings."""

import os


class Settings:
    """Central configuration for the local server."""

    APP_NAME: str = "Unergy Local Server"
    VERSION: str = "0.1.0"

    # Server
    HOST: str = os.getenv("LOCAL_SERVER_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("LOCAL_SERVER_PORT", "8000"))

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Remote server (WebSocket hub)
    REMOTE_SERVER_URL: str = os.getenv("REMOTE_SERVER_URL", "ws://localhost:8001/ws")

    # WiFi positioning module path (read-only, never modify)
    WIFI_POSITIONING_MODULE: str = "wifipos"


settings = Settings()
