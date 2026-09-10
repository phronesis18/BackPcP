import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.contrats_service import to_dossier_public, to_relance_public
from app.models import (
    ContratsDossierPublic,
    RecouvrementConfigPublic,
    RecouvrementPhaseConfig,
    RelanceCreate,
    RelancePublic,
)
from app.recouvrement import PHASES

router = APIRouter(prefix="/recouvrement", tags=["recouvrement"])


def _require_back_office(current_user: CurrentUser) -> None:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Accès non autorisé")


@router.get("/config", response_model=RecouvrementConfigPublic)
def read_config(current_user: CurrentUser) -> Any:
    """Seuils du Recover Bot (J+3 SMS, J+7 WhatsApp, J+15 appel, J+30 coupe-moteur)."""
    _require_back_office(current_user)
    return RecouvrementConfigPublic(
        phases=[
            RecouvrementPhaseConfig(
                index=p.index, canal=p.canal, label=p.label, seuil_jours=p.seuil_jours
            )
            for p in PHASES
        ]
    )


@router.get("/dossiers", response_model=ContratsDossierPublic)
def read_dossiers_en_retard(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Dossiers actuellement en retard de paiement, avec la phase du Recover Bot
    en cours. Rattrape au passage les relances automatiques dues (voir
    app.recouvrement.ensure_relance_backlog) — l'état avance avec le temps
    réel, sans tâche planifiée.
    """
    _require_back_office(current_user)
    contrats = crud.get_contrats(session=session)
    dossiers = [to_dossier_public(session, c) for c in contrats]
    en_retard = [d for d in dossiers if d.jours_retard > 0]
    en_retard.sort(key=lambda d: d.jours_retard, reverse=True)
    return ContratsDossierPublic(data=en_retard, count=len(en_retard))


@router.post("/{contrat_id}/relance", response_model=RelancePublic, status_code=201)
def creer_relance_manuelle(
    session: SessionDep,
    current_user: CurrentUser,
    contrat_id: uuid.UUID,
    relance_in: RelanceCreate,
) -> Any:
    """Déclenche manuellement un canal de relance (SMS, WhatsApp, appel...)."""
    _require_back_office(current_user)
    contrat = crud.get_contrat_by_id(session=session, contrat_id=contrat_id)
    if not contrat:
        raise HTTPException(status_code=404, detail="Contrat introuvable")
    relance = crud.create_relance(
        session=session,
        contrat_id=contrat_id,
        relance_in=relance_in,
        created_by=current_user.id,
    )
    return to_relance_public(session, relance)
