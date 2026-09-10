import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import (
    ActionRecouvrement,
    ActionRecouvrementCreate,
    ActionRecouvrementPublic,
    ActionsRecouvrementPublic,
    Demande,
    DossierRecouvrementPublic,
    DossiersRecouvrementPublic,
    EcheancePublic,
    EcheancesPublic,
    Message,
    RecouvrementInfo,
    TYPES_ACTION_RECOUVREMENT,
    User,
)
from app.recouvrement import compute_recouvrement

router = APIRouter(prefix="/demandes", tags=["recouvrement"])
dossiers_router = APIRouter(prefix="/recouvrement", tags=["recouvrement"])


def _require_access(demande: Demande, user: User) -> None:
    if not (user.is_superuser or user.is_admin) and demande.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")


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


@router.get("/{demande_id}/echeances", response_model=EcheancesPublic)
def read_echeances(session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID) -> Any:
    """
    Échéancier réel du dossier, généré à la signature du contrat. Vide tant
    que le contrat n'est pas signé.
    """
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    _require_access(demande, current_user)
    echeances = crud.get_echeances(session=session, demande_id=demande_id)
    return EcheancesPublic(
        data=[EcheancePublic.model_validate(e) for e in echeances], count=len(echeances)
    )


@router.post(
    "/{demande_id}/echeances/{echeance_id}/marquer-payee", response_model=EcheancePublic
)
def marquer_echeance_payee(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    echeance_id: uuid.UUID,
) -> Any:
    """
    Constat manuel de paiement par un admin — il n'existe aucun webhook
    Mobile Money branché à ce jour, donc rien ne marque une échéance payée
    automatiquement.
    """
    _require_admin(current_user)
    echeance = crud.get_echeance(session=session, echeance_id=echeance_id)
    if not echeance or echeance.demande_id != demande_id:
        raise HTTPException(status_code=404, detail="Échéance introuvable")
    if echeance.payee:
        return echeance
    return crud.marquer_echeance_payee(session=session, echeance=echeance)


@router.get("/{demande_id}/recouvrement", response_model=RecouvrementInfo)
def read_recouvrement(
    session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID
) -> Any:
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    _require_access(demande, current_user)
    echeances = crud.get_echeances(session=session, demande_id=demande_id)
    actions = crud.get_actions_recouvrement(session=session, demande_id=demande_id)
    info = compute_recouvrement(echeances, actions)
    if info["derniere_action"] is not None:
        info["derniere_action"] = _action_to_public(session, info["derniere_action"])
    return RecouvrementInfo(**info)


@router.get("/{demande_id}/recouvrement/actions", response_model=ActionsRecouvrementPublic)
def read_actions_recouvrement(
    session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID
) -> Any:
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    _require_access(demande, current_user)
    actions = crud.get_actions_recouvrement(session=session, demande_id=demande_id)
    return ActionsRecouvrementPublic(
        data=[_action_to_public(session, a) for a in actions], count=len(actions)
    )


@router.post(
    "/{demande_id}/recouvrement/actions",
    response_model=ActionRecouvrementPublic,
    status_code=201,
)
def create_action_recouvrement(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    action_in: ActionRecouvrementCreate,
) -> Any:
    """
    Consigne une action de relance décidée par un admin (SMS, WhatsApp,
    appel, mise en demeure, coupure moteur, réactivation, contentieux).
    Aucun message ni commande matérielle n'est réellement envoyé — c'est un
    constat manuel, pas une automatisation.
    """
    _require_admin(current_user)
    if action_in.type not in TYPES_ACTION_RECOUVREMENT:
        raise HTTPException(status_code=422, detail="Type d'action inconnu")
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    action = crud.create_action_recouvrement(
        session=session,
        demande_id=demande_id,
        created_by_id=current_user.id,
        action_in=action_in,
    )
    return _action_to_public(session, action)


@router.delete("/{demande_id}/echeances/{echeance_id}", response_model=Message)
def annuler_paiement_echeance(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    echeance_id: uuid.UUID,
) -> Any:
    """Annule un constat de paiement erroné (remet l'échéance en impayée)."""
    _require_admin(current_user)
    echeance = crud.get_echeance(session=session, echeance_id=echeance_id)
    if not echeance or echeance.demande_id != demande_id:
        raise HTTPException(status_code=404, detail="Échéance introuvable")
    crud.annuler_echeance_payee(session=session, echeance=echeance)
    return Message(message="Paiement annulé")


@dossiers_router.get("/dossiers", response_model=DossiersRecouvrementPublic)
def list_dossiers_recouvrement(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Tous les dossiers ayant au moins une échéance en retard aujourd'hui,
    calculé depuis l'échéancier réel — pas de bot automatique, seulement le
    même calcul que la fiche recouvrement d'un dossier.
    """
    _require_admin(current_user)
    demandes = crud.list_demandes_avec_echeancier(session=session)
    resume = {"j1_15": 0, "j16_30": 0, "coupe_moteur": 0}
    data: list[DossierRecouvrementPublic] = []
    for demande in demandes:
        echeances = crud.get_echeances(session=session, demande_id=demande.id)
        actions = crud.get_actions_recouvrement(session=session, demande_id=demande.id)
        info = compute_recouvrement(echeances, actions)
        if not info["en_retard"]:
            continue
        if info["phase"] in resume:
            resume[info["phase"]] += 1
        if info["derniere_action"] is not None:
            info = {**info, "derniere_action": _action_to_public(session, info["derniere_action"])}
        data.append(
            DossierRecouvrementPublic(
                demande_id=demande.id,
                client_nom=f"{demande.prenom} {demande.nom}".strip(),
                created_at=demande.created_at,
                recouvrement=RecouvrementInfo(**info),
            )
        )
    data.sort(key=lambda d: d.recouvrement.jours_retard, reverse=True)
    return DossiersRecouvrementPublic(data=data, resume=resume)
