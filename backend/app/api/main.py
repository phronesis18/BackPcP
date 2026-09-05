from fastapi import APIRouter

from app.api.routes import catalogue, login, private, users, utils, demandes
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(demandes.router)
api_router.include_router(catalogue.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
