"""Unergy Local Server — FastAPI application entry point.

Run with:
    cd local-server
    uvicorn main:app --reload --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, instructions, spaces
from app.core.config import settings
from app.repositories.space_repository import SpaceRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.space_service import SpaceService
from app.services.wifi_integration_service import WiFiIntegrationService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Instantiate repositories
# ---------------------------------------------------------------------------
user_repo = UserRepository()
space_repo = SpaceRepository()  # JSON-persistent at data/spaces.json

# ---------------------------------------------------------------------------
# Instantiate services
# ---------------------------------------------------------------------------
wifi_service = WiFiIntegrationService()
auth_service = AuthService(user_repo)
space_service = SpaceService(space_repo, wifi_service)

# ---------------------------------------------------------------------------
# Wire services into route modules
# ---------------------------------------------------------------------------
auth.set_auth_service(auth_service)
spaces.set_space_service(space_service)
instructions.set_wifi_service(wifi_service)

# ---------------------------------------------------------------------------
# Create FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "Backend local para la plataforma Unergy. "
        "Gestiona usuarios, espacios y se integra con el módulo "
        "wifi-positioning para posicionamiento indoor."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(spaces.router)
app.include_router(instructions.router)


@app.get("/", tags=["health"])
def health_check():
    """Health check / root endpoint."""
    return {
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running",
        "remote_server": settings.REMOTE_SERVER_URL,
    }
