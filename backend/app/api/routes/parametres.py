from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import ParametresFinanciersPublic, ParametresFinanciersUpdate

router = APIRouter(prefix="/parametres", tags=["parametres"])


@router.get("/financiers", response_model=ParametresFinanciersPublic)
def read_parametres_financiers(session: SessionDep) -> Any:
    """
    Taux TEG et taux d'apport appliqués par le simulateur et le formulaire de demande.
    """
    return crud.get_or_create_parametres_financiers(session=session)


@router.patch("/financiers", response_model=ParametresFinanciersPublic)
def update_parametres_financiers(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    parametres_in: ParametresFinanciersUpdate,
) -> Any:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    db_parametres = crud.get_or_create_parametres_financiers(session=session)
    return crud.update_parametres_financiers(
        session=session, db_parametres=db_parametres, parametres_in=parametres_in
    )
