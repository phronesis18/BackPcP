from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import (
    GrilleTauxDureePublic,
    GrilleTauxDureeUpsert,
    ParametresFinanciersPublic,
    ParametresFinanciersUpdate,
)

router = APIRouter(prefix="/parametres", tags=["parametres"])


@router.get("/financiers", response_model=ParametresFinanciersPublic)
def read_parametres_financiers(session: SessionDep) -> Any:
    """
    Seuil de scoring auto et bornes de montant financé appliqués par le
    formulaire de demande. Le TEG et l'apport sont gérés par la grille des
    taux par durée (voir /parametres/grille-taux).
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


@router.get("/grille-taux", response_model=list[GrilleTauxDureePublic])
def read_grille_taux(session: SessionDep) -> Any:
    """
    Grille des TEG annuels et apports minimums applicables, par durée de
    financement (mois). Appliquée par le simulateur public et le formulaire
    de demande.
    """
    return crud.get_grille_taux(session=session)


@router.put("/grille-taux", response_model=list[GrilleTauxDureePublic])
def update_grille_taux(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    grille_in: list[GrilleTauxDureeUpsert],
) -> Any:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    if not grille_in:
        raise HTTPException(status_code=422, detail="La grille ne peut pas être vide.")
    for item in grille_in:
        if item.duree_mois <= 0:
            raise HTTPException(status_code=422, detail="Durée invalide dans la grille.")
        if item.taux_teg_annuel <= 0:
            raise HTTPException(status_code=422, detail="TEG invalide dans la grille.")
        if not (0 <= item.taux_apport_min <= 1):
            raise HTTPException(
                status_code=422, detail="Apport minimum invalide dans la grille."
            )
    return crud.upsert_grille_taux(session=session, items=grille_in)
