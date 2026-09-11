from fastapi import APIRouter

from app.api.routes import (
    catalogue,
    fleet,
    login,
    messagerie,
    messages,
    parametres,
    private,
    recouvrement,
    users,
    utils,
    demandes,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(demandes.router)
api_router.include_router(catalogue.router)
api_router.include_router(parametres.router)
api_router.include_router(messages.router)
api_router.include_router(messagerie.router)
api_router.include_router(recouvrement.router)
api_router.include_router(recouvrement.dossiers_router)
api_router.include_router(fleet.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
