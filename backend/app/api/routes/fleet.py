import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import (
    ActionRecouvrement,
    ActionRecouvrementPublic,
    Demande,
    FicheVehiculePublic,
    RecouvrementInfo,
    User,
    VehiculeFlotte,
    VehiculeFlottePublic,
    VehiculeFlotteUpdate,
    VehiculesFlottePublic,
)
from app.recouvrement import compute_recouvrement, flotte_statut

router = APIRouter(prefix="/fleet", tags=["fleet"])


def _require_admin(user: User) -> None:
    if not (user.is_superuser or user.is_admin):
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _action_to_public(session: SessionDep, action: ActionRecouvrement) -> ActionRecouvrementPublic:
    user = session.get(User, action.created_by_id)
    created_by_nom = (user.full_name or user.email) if user else "Utilisateur supprimé"
    return ActionRecouvrementPublic(
        id=action.id,
        demande_id=action.demande_id,
        type=action.type,
        note=action.note,
        created_by_nom=created_by_nom,
        created_at=action.created_at,
    )


def _vehicule_to_public(
    session: SessionDep, vehicule: VehiculeFlotte, demande: Demande
) -> VehiculeFlottePublic:
    echeances = crud.get_echeances(session=session, demande_id=demande.id)
    actions = crud.get_actions_recouvrement(session=session, demande_id=demande.id)
    info = compute_recouvrement(echeances, actions)
    conducteur_telephone = demande.owner.phone if demande.owner else None
    return VehiculeFlottePublic(
        id=vehicule.id,
        demande_id=vehicule.demande_id,
        plaque=vehicule.plaque,
        position_label=vehicule.position_label,
        marque=demande.marque,
        modele=demande.modele,
        annee=demande.annee,
        conducteur_nom=f"{demande.prenom} {demande.nom}".strip(),
        conducteur_telephone=conducteur_telephone,
        position_maj_le=vehicule.position_maj_le,
        statut=flotte_statut(info),
        moteur_coupe=info["moteur_coupe"],
        jours_retard=info["jours_retard"],
        montant_du=info["montant_du"],
    )


@router.get("/vehicules", response_model=VehiculesFlottePublic)
def list_vehicules(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Parc de véhicules financés sous contrat signé. Position et plaque sont
    saisies à la main par un admin — il n'existe aucun boîtier GPS connecté
    à ce jour, donc aucune coordonnée n'est jamais inventée ici.
    """
    _require_admin(current_user)
    vehicules = crud.list_vehicules_flotte(session=session)
    data = []
    for vehicule in vehicules:
        demande = crud.get_demande(session=session, demande_id=vehicule.demande_id)
        if demande:
            data.append(_vehicule_to_public(session, vehicule, demande))
    return VehiculesFlottePublic(data=data, count=len(data))


@router.get("/vehicules/{demande_id}", response_model=FicheVehiculePublic)
def read_vehicule(session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID) -> Any:
    _require_admin(current_user)
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    vehicule = crud.get_vehicule_flotte(session=session, demande_id=demande_id)
    if not vehicule:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    echeances = crud.get_echeances(session=session, demande_id=demande_id)
    actions = crud.get_actions_recouvrement(session=session, demande_id=demande_id)
    info = compute_recouvrement(echeances, actions)
    derniere_action = info["derniere_action"]
    if derniere_action is not None:
        info = {**info, "derniere_action": _action_to_public(session, derniere_action)}
    return FicheVehiculePublic(
        vehicule=_vehicule_to_public(session, vehicule, demande),
        recouvrement=RecouvrementInfo(**info),
        actions=[_action_to_public(session, a) for a in actions],
    )


@router.patch("/vehicules/{demande_id}", response_model=VehiculeFlottePublic)
def update_vehicule(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    vehicule_in: VehiculeFlotteUpdate,
) -> Any:
    """Saisie manuelle de la plaque et/ou de la position par un admin."""
    _require_admin(current_user)
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    vehicule = crud.get_vehicule_flotte(session=session, demande_id=demande_id)
    if not vehicule:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    vehicule = crud.update_vehicule_flotte(
        session=session,
        vehicule=vehicule,
        vehicule_in=vehicule_in,
        updated_by_id=current_user.id,
    )
    return _vehicule_to_public(session, vehicule, demande)
