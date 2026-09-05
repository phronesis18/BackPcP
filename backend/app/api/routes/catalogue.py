import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Marque,
    MarqueCreate,
    MarquePublic,
    MarquesPublic,
    MarqueUpdate,
    Message,
    Modele,
    ModeleAnnee,
    ModeleAnneeCreate,
    ModeleAnneePublic,
    ModeleAnneesPublic,
    ModeleAnneeUpdate,
    ModeleCreate,
    ModelePublic,
    ModelesPublic,
    ModeleUpdate,
)

router = APIRouter(prefix="/catalogue", tags=["catalogue"])


def _require_admin(current_user: CurrentUser) -> None:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )


# --- Marques ---------------------------------------------------------------


@router.get("/marques", response_model=MarquesPublic)
def read_marques(session: SessionDep) -> Any:
    marques, count = crud.get_marques(session=session)
    return MarquesPublic(data=marques, count=count)


@router.post("/marques", response_model=MarquePublic)
def create_marque(
    *, session: SessionDep, current_user: CurrentUser, marque_in: MarqueCreate
) -> Any:
    _require_admin(current_user)
    existing = crud.get_marque_by_nom(session=session, nom=marque_in.nom)
    if existing:
        raise HTTPException(status_code=400, detail="Cette marque existe déjà.")
    return crud.create_marque(session=session, marque_in=marque_in)


@router.patch("/marques/{marque_id}", response_model=MarquePublic)
def update_marque(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    marque_id: uuid.UUID,
    marque_in: MarqueUpdate,
) -> Any:
    _require_admin(current_user)
    db_marque = session.get(Marque, marque_id)
    if not db_marque:
        raise HTTPException(status_code=404, detail="Marque introuvable.")
    if marque_in.nom:
        existing = crud.get_marque_by_nom(session=session, nom=marque_in.nom)
        if existing and existing.id != marque_id:
            raise HTTPException(status_code=400, detail="Cette marque existe déjà.")
    return crud.update_marque(session=session, db_marque=db_marque, marque_in=marque_in)


@router.delete("/marques/{marque_id}", response_model=Message)
def delete_marque(
    session: SessionDep, current_user: CurrentUser, marque_id: uuid.UUID
) -> Any:
    _require_admin(current_user)
    marque = session.get(Marque, marque_id)
    if not marque:
        raise HTTPException(status_code=404, detail="Marque introuvable.")
    session.delete(marque)
    session.commit()
    return Message(message="Marque supprimée avec succès")


# --- Modeles -----------------------------------------------------------------


@router.get("/marques/{marque_id}/modeles", response_model=ModelesPublic)
def read_modeles(session: SessionDep, marque_id: uuid.UUID) -> Any:
    modeles, count = crud.get_modeles(session=session, marque_id=marque_id)
    return ModelesPublic(data=modeles, count=count)


@router.post("/modeles", response_model=ModelePublic)
def create_modele(
    *, session: SessionDep, current_user: CurrentUser, modele_in: ModeleCreate
) -> Any:
    _require_admin(current_user)
    marque = session.get(Marque, modele_in.marque_id)
    if not marque:
        raise HTTPException(status_code=404, detail="Marque introuvable.")
    existing = crud.get_modele_by_nom(
        session=session, marque_id=modele_in.marque_id, nom=modele_in.nom
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Ce modèle existe déjà pour cette marque."
        )
    return crud.create_modele(session=session, modele_in=modele_in)


@router.patch("/modeles/{modele_id}", response_model=ModelePublic)
def update_modele(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    modele_id: uuid.UUID,
    modele_in: ModeleUpdate,
) -> Any:
    _require_admin(current_user)
    db_modele = session.get(Modele, modele_id)
    if not db_modele:
        raise HTTPException(status_code=404, detail="Modèle introuvable.")
    if modele_in.nom:
        existing = crud.get_modele_by_nom(
            session=session, marque_id=db_modele.marque_id, nom=modele_in.nom
        )
        if existing and existing.id != modele_id:
            raise HTTPException(
                status_code=400, detail="Ce modèle existe déjà pour cette marque."
            )
    return crud.update_modele(session=session, db_modele=db_modele, modele_in=modele_in)


@router.delete("/modeles/{modele_id}", response_model=Message)
def delete_modele(
    session: SessionDep, current_user: CurrentUser, modele_id: uuid.UUID
) -> Any:
    _require_admin(current_user)
    modele = session.get(Modele, modele_id)
    if not modele:
        raise HTTPException(status_code=404, detail="Modèle introuvable.")
    session.delete(modele)
    session.commit()
    return Message(message="Modèle supprimé avec succès")


# --- Annees ------------------------------------------------------------------


@router.get("/modeles/{modele_id}/annees", response_model=ModeleAnneesPublic)
def read_modele_annees(session: SessionDep, modele_id: uuid.UUID) -> Any:
    annees, count = crud.get_modele_annees(session=session, modele_id=modele_id)
    return ModeleAnneesPublic(data=annees, count=count)


@router.post("/annees", response_model=ModeleAnneePublic)
def create_modele_annee(
    *, session: SessionDep, current_user: CurrentUser, annee_in: ModeleAnneeCreate
) -> Any:
    _require_admin(current_user)
    modele = session.get(Modele, annee_in.modele_id)
    if not modele:
        raise HTTPException(status_code=404, detail="Modèle introuvable.")
    existing = crud.get_modele_annee_by_annee(
        session=session, modele_id=annee_in.modele_id, annee=annee_in.annee
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Cette année existe déjà pour ce modèle."
        )
    return crud.create_modele_annee(session=session, annee_in=annee_in)


@router.patch("/annees/{annee_id}", response_model=ModeleAnneePublic)
def update_modele_annee(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    annee_id: uuid.UUID,
    annee_in: ModeleAnneeUpdate,
) -> Any:
    _require_admin(current_user)
    db_annee = session.get(ModeleAnnee, annee_id)
    if not db_annee:
        raise HTTPException(status_code=404, detail="Année introuvable.")
    if annee_in.annee is not None:
        existing = crud.get_modele_annee_by_annee(
            session=session, modele_id=db_annee.modele_id, annee=annee_in.annee
        )
        if existing and existing.id != annee_id:
            raise HTTPException(
                status_code=400, detail="Cette année existe déjà pour ce modèle."
            )
    return crud.update_modele_annee(session=session, db_annee=db_annee, annee_in=annee_in)


@router.delete("/annees/{annee_id}", response_model=Message)
def delete_modele_annee(
    session: SessionDep, current_user: CurrentUser, annee_id: uuid.UUID
) -> Any:
    _require_admin(current_user)
    annee = session.get(ModeleAnnee, annee_id)
    if not annee:
        raise HTTPException(status_code=404, detail="Année introuvable.")
    session.delete(annee)
    session.commit()
    return Message(message="Année supprimée avec succès")
