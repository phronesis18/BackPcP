from fastapi import APIRouter

from app.api.routes import (
    catalogue,
    contrats,
    demandes,
    investissements,
    login,
    messages,
    parametres,
    private,
    recouvrement,
    users,
    utils,
    vehicules,
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
api_router.include_router(contrats.router)
api_router.include_router(recouvrement.router)
api_router.include_router(vehicules.router)
api_router.include_router(investissements.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
