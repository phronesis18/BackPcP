import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Distribution,
    DistributionCreate,
    DistributionPublic,
    DistributionUpdate,
    FondsPerformancePublic,
    InvestisseurAdminRowPublic,
    InvestisseurDashboardPublic,
    InvestisseurProfilPublic,
    InvestisseurProfilUpdate,
    InvestisseursAdminPublic,
    Message,
    RepartitionMarquePublic,
    User,
)

router = APIRouter(prefix="/investisseurs", tags=["investissements"])


def _require_staff(current_user: User) -> None:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _require_dashboard_access(target: User, current_user: User) -> None:
    is_staff = current_user.is_superuser or current_user.is_admin
    if not is_staff and current_user.id != target.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _get_investisseur(session: SessionDep, investisseur_id: uuid.UUID) -> User:
    user = session.get(User, investisseur_id)
    if not user or not user.is_investisseur:
        raise HTTPException(status_code=404, detail="Investisseur introuvable")
    return user


def _to_dashboard_public(data: dict) -> InvestisseurDashboardPublic:
    return InvestisseurDashboardPublic(
        investisseur_id=data["investisseur_id"],
        montant_investi=data["montant_investi"],
        date_investissement=data["date_investissement"],
        dividendes_recus=data["dividendes_recus"],
        rendement_ytd_pct=data["rendement_ytd_pct"],
        tri_calcule_pct=data["tri_calcule_pct"],
        prochain_versement=(
            DistributionPublic.model_validate(data["prochain_versement"])
            if data["prochain_versement"]
            else None
        ),
        distributions=[DistributionPublic.model_validate(d) for d in data["distributions"]],
        repartition_marques=[
            RepartitionMarquePublic(**r) for r in data["repartition_marques"]
        ],
        fonds=FondsPerformancePublic(**data["fonds"]),
    )


@router.get("", response_model=InvestisseursAdminPublic)
def read_investisseurs(session: SessionDep, current_user: CurrentUser) -> Any:
    """Liste de gestion admin : capital investi et prochain versement de chaque investisseur."""
    _require_staff(current_user)
    rows: list[InvestisseurAdminRowPublic] = []
    for user in crud.list_investisseurs(session=session):
        dashboard = crud.get_investisseur_dashboard(session=session, investisseur_id=user.id)
        rows.append(
            InvestisseurAdminRowPublic(
                investisseur_id=user.id,
                nom=user.full_name or user.email,
                email=user.email,
                montant_investi=dashboard["montant_investi"],
                date_investissement=dashboard["date_investissement"],
                dividendes_recus=dashboard["dividendes_recus"],
                prochain_versement=(
                    DistributionPublic.model_validate(dashboard["prochain_versement"])
                    if dashboard["prochain_versement"]
                    else None
                ),
            )
        )
    return InvestisseursAdminPublic(data=rows)


@router.get("/{investisseur_id}/dashboard", response_model=InvestisseurDashboardPublic)
def read_dashboard(
    session: SessionDep, current_user: CurrentUser, investisseur_id: uuid.UUID
) -> Any:
    target = _get_investisseur(session, investisseur_id)
    _require_dashboard_access(target, current_user)
    data = crud.get_investisseur_dashboard(session=session, investisseur_id=investisseur_id)
    return _to_dashboard_public(data)


@router.patch("/{investisseur_id}/profil", response_model=InvestisseurProfilPublic)
def update_profil(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    investisseur_id: uuid.UUID,
    profil_in: InvestisseurProfilUpdate,
) -> Any:
    _require_staff(current_user)
    _get_investisseur(session, investisseur_id)
    profil = crud.upsert_investisseur_profil(
        session=session, investisseur_id=investisseur_id, profil_in=profil_in
    )
    return InvestisseurProfilPublic.model_validate(profil)


@router.post(
    "/{investisseur_id}/distributions", response_model=DistributionPublic, status_code=201
)
def create_distribution_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    investisseur_id: uuid.UUID,
    distribution_in: DistributionCreate,
) -> Any:
    _require_staff(current_user)
    _get_investisseur(session, investisseur_id)
    distribution = crud.create_distribution(
        session=session, investisseur_id=investisseur_id, distribution_in=distribution_in
    )
    return DistributionPublic.model_validate(distribution)


def _get_distribution(
    session: SessionDep, investisseur_id: uuid.UUID, distribution_id: uuid.UUID
) -> Distribution:
    distribution = crud.get_distribution(session=session, distribution_id=distribution_id)
    if not distribution or distribution.investisseur_id != investisseur_id:
        raise HTTPException(status_code=404, detail="Distribution introuvable")
    return distribution


@router.patch(
    "/{investisseur_id}/distributions/{distribution_id}", response_model=DistributionPublic
)
def update_distribution_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    investisseur_id: uuid.UUID,
    distribution_id: uuid.UUID,
    distribution_in: DistributionUpdate,
) -> Any:
    _require_staff(current_user)
    distribution = _get_distribution(session, investisseur_id, distribution_id)
    distribution = crud.update_distribution(
        session=session, distribution=distribution, distribution_in=distribution_in
    )
    return DistributionPublic.model_validate(distribution)


@router.delete("/{investisseur_id}/distributions/{distribution_id}", response_model=Message)
def delete_distribution_route(
    session: SessionDep,
    current_user: CurrentUser,
    investisseur_id: uuid.UUID,
    distribution_id: uuid.UUID,
) -> Any:
    _require_staff(current_user)
    distribution = _get_distribution(session, investisseur_id, distribution_id)
    crud.delete_distribution(session=session, distribution=distribution)
    return Message(message="Distribution supprimée")
