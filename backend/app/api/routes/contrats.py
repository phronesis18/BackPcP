import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.contrats_service import to_dossier_public, to_echeance_public, to_relance_public
from app.models import (
    ContratDossierPublic,
    ContratsDossierPublic,
    EcheancePublic,
    EcheancesPublic,
    PaiementPayer,
    RelancesPublic,
)

router = APIRouter(prefix="/contrats", tags=["contrats"])


def _require_back_office(current_user: CurrentUser) -> None:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _get_contrat_or_404(session: SessionDep, contrat_id: uuid.UUID):
    contrat = crud.get_contrat_by_id(session=session, contrat_id=contrat_id)
    if not contrat:
        raise HTTPException(status_code=404, detail="Contrat introuvable")
    return contrat


def _require_contrat_access(current_user: CurrentUser, contrat) -> None:
    is_back_office = current_user.is_superuser or current_user.is_admin
    if not is_back_office and contrat.demande.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")


@router.get("/", response_model=ContratsDossierPublic)
def read_contrats(session: SessionDep, current_user: CurrentUser) -> Any:
    """Portefeuille de tous les contrats signés (back-office)."""
    _require_back_office(current_user)
    contrats = crud.get_contrats(session=session)
    data = [to_dossier_public(session, c) for c in contrats]
    return ContratsDossierPublic(data=data, count=len(data))


@router.get("/{contrat_id}", response_model=ContratDossierPublic)
def read_contrat(session: SessionDep, current_user: CurrentUser, contrat_id: uuid.UUID) -> Any:
    contrat = _get_contrat_or_404(session, contrat_id)
    _require_contrat_access(current_user, contrat)
    return to_dossier_public(session, contrat)


@router.get("/{contrat_id}/echeances", response_model=EcheancesPublic)
def read_echeances(session: SessionDep, current_user: CurrentUser, contrat_id: uuid.UUID) -> Any:
    contrat = _get_contrat_or_404(session, contrat_id)
    _require_contrat_access(current_user, contrat)
    paiements = crud.get_paiements(session=session, contrat_id=contrat_id)
    return EcheancesPublic(data=[to_echeance_public(p) for p in paiements], count=len(paiements))


@router.get("/{contrat_id}/relances", response_model=RelancesPublic)
def read_relances(session: SessionDep, current_user: CurrentUser, contrat_id: uuid.UUID) -> Any:
    """Historique complet des relances/commandes d'un contrat (SMS, WhatsApp, appel, coupe-moteur…)."""
    contrat = _get_contrat_or_404(session, contrat_id)
    _require_contrat_access(current_user, contrat)
    relances = crud.get_relances(session=session, contrat_id=contrat_id)
    data = [to_relance_public(session, r) for r in relances]
    return RelancesPublic(data=data, count=len(data))


@router.post("/{contrat_id}/echeances/{index}/payer", response_model=EcheancePublic)
def payer_echeance(
    session: SessionDep,
    current_user: CurrentUser,
    contrat_id: uuid.UUID,
    index: int,
    payer_in: PaiementPayer | None = None,
) -> Any:
    """
    Marque une échéance comme payée — la simulation manuelle du webhook
    MTN MoMo / Moov Africa qu'on n'a pas en l'absence d'intégration réelle.
    """
    _require_back_office(current_user)
    _get_contrat_or_404(session, contrat_id)
    paiements = crud.get_paiements(session=session, contrat_id=contrat_id)
    paiement = next((p for p in paiements if p.index == index), None)
    if not paiement:
        raise HTTPException(status_code=404, detail="Échéance introuvable")
    if paiement.paid_at is not None:
        raise HTTPException(status_code=409, detail="Cette échéance est déjà payée")
    mode = payer_in.mode_paiement if payer_in else "mtn_momo"
    updated = crud.pay_echeance(session=session, paiement=paiement, mode_paiement=mode)
    return to_echeance_public(updated)
