import random
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud, gps_simulator
from app.api.deps import CurrentUser, SessionDep
from app.contrats_service import to_vehicule_detail_public, to_vehicule_public
from app.models import (
    AlertePublic,
    AlertesPublic,
    CanalRelance,
    FleetStatsPublic,
    RelanceCreate,
    TrajetPublic,
    TrajetsPublic,
    VehiculeDetailPublic,
    VehiculesPublic,
)

router = APIRouter(prefix="/vehicules", tags=["vehicules"])


def _require_fleet_access(current_user: CurrentUser) -> None:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _get_contrat_or_404(session: SessionDep, contrat_id: uuid.UUID):
    contrat = crud.get_contrat_by_id(session=session, contrat_id=contrat_id)
    if not contrat:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    return contrat


@router.get("/", response_model=VehiculesPublic)
def read_vehicules(session: SessionDep, current_user: CurrentUser) -> Any:
    _require_fleet_access(current_user)
    contrats = crud.get_contrats(session=session)
    data = [to_vehicule_public(session, c) for c in contrats]
    return VehiculesPublic(data=data, count=len(data))


@router.get("/stats", response_model=FleetStatsPublic)
def read_fleet_stats(session: SessionDep, current_user: CurrentUser) -> Any:
    _require_fleet_access(current_user)
    contrats = crud.get_contrats(session=session)

    semaines = []
    for offset in range(5, -1, -1):
        total_km = sum(
            gps_simulator.simulate_semaine(c.id, offset)["distance_km"] for c in contrats
        )
        semaines.append({"semaine": "S" if offset == 0 else f"S-{offset}", "km": round(total_km, 1)})

    distance_30j = sum(w["km"] for w in semaines[-5:])
    trajets_30j = sum(
        gps_simulator.simulate_semaine(c.id, offset)["nb_trajets"]
        for c in contrats
        for offset in range(5)
    )
    vitesse_moyenne = (
        round(sum(gps_simulator.average_speed_kmh(c.id) for c in contrats) / len(contrats), 1)
        if contrats
        else 0.0
    )
    disponibilite = round(random.Random("pcp-fleet-disponibilite-gps").uniform(97.5, 99.8), 1)

    return FleetStatsPublic(
        nb_vehicules=len(contrats),
        distance_totale_km=round(distance_30j, 1),
        nb_trajets=trajets_30j,
        vitesse_moyenne_kmh=vitesse_moyenne,
        disponibilite_gps_pct=disponibilite,
        distance_par_semaine=semaines,
    )


@router.get("/{contrat_id}", response_model=VehiculeDetailPublic)
def read_vehicule(session: SessionDep, current_user: CurrentUser, contrat_id: uuid.UUID) -> Any:
    _require_fleet_access(current_user)
    contrat = _get_contrat_or_404(session, contrat_id)
    return to_vehicule_detail_public(session, contrat)


@router.get("/{contrat_id}/historique", response_model=TrajetsPublic)
def read_historique(session: SessionDep, current_user: CurrentUser, contrat_id: uuid.UUID) -> Any:
    _require_fleet_access(current_user)
    _get_contrat_or_404(session, contrat_id)
    trajets = gps_simulator.simulate_historique(contrat_id, datetime.now(timezone.utc))
    data = [
        TrajetPublic(
            depart=t.depart,
            arrivee=t.arrivee,
            debut=t.debut,
            duree_min=t.duree_min,
            distance_km=t.distance_km,
            vitesse_max=t.vitesse_max,
        )
        for t in trajets
    ]
    return TrajetsPublic(data=data, count=len(data))


@router.get("/{contrat_id}/alertes", response_model=AlertesPublic)
def read_alertes(session: SessionDep, current_user: CurrentUser, contrat_id: uuid.UUID) -> Any:
    _require_fleet_access(current_user)
    _get_contrat_or_404(session, contrat_id)
    alertes = gps_simulator.simulate_alertes(contrat_id, datetime.now(timezone.utc))
    data = [
        AlertePublic(type=a.type, message=a.message, survenue_a=a.survenue_a) for a in alertes
    ]
    return AlertesPublic(data=data, count=len(data))


@router.post("/{contrat_id}/cutoff", response_model=VehiculeDetailPublic)
def activer_coupe_moteur(
    session: SessionDep, current_user: CurrentUser, contrat_id: uuid.UUID
) -> Any:
    """Coupe-moteur à distance — commande tracée, admin obligatoire."""
    _require_fleet_access(current_user)
    contrat = _get_contrat_or_404(session, contrat_id)
    if contrat.cutoff_active:
        raise HTTPException(status_code=409, detail="Le coupe-moteur est déjà actif")
    contrat.cutoff_active = True
    session.add(contrat)
    crud.create_relance(
        session=session,
        contrat_id=contrat_id,
        relance_in=RelanceCreate(canal=CanalRelance.coupe_moteur, note="Coupe-moteur manuel"),
        created_by=current_user.id,
    )
    session.commit()
    session.refresh(contrat)
    return to_vehicule_detail_public(session, contrat)


@router.post("/{contrat_id}/restore", response_model=VehiculeDetailPublic)
def reactiver_moteur(
    session: SessionDep, current_user: CurrentUser, contrat_id: uuid.UUID
) -> Any:
    """Réactivation du moteur — commande tracée, admin obligatoire."""
    _require_fleet_access(current_user)
    contrat = _get_contrat_or_404(session, contrat_id)
    if not contrat.cutoff_active:
        raise HTTPException(status_code=409, detail="Le moteur n'est pas coupé")
    contrat.cutoff_active = False
    session.add(contrat)
    crud.create_relance(
        session=session,
        contrat_id=contrat_id,
        relance_in=RelanceCreate(canal=CanalRelance.reactivation, note="Réactivation manuelle"),
        created_by=current_user.id,
    )
    session.commit()
    session.refresh(contrat)
    return to_vehicule_detail_public(session, contrat)
