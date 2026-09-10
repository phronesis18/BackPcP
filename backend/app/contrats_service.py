"""
Composition partagée entre les routes /contrats, /recouvrement et /vehicules :
les trois exposent des vues différentes du même contrat signé (dossier actif,
retard de paiement, véhicule GPS), donc elles partagent le même calcul de
contexte plutôt que de le dupliquer trois fois.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlmodel import Session

from app import crud, gps_simulator
from app.models import (
    Contrat,
    ContratDossierPublic,
    Demande,
    EcheancePublic,
    Paiement,
    PositionPublic,
    Relance,
    StatsDuJourPublic,
    VehiculeDetailPublic,
    VehiculePublic,
)
from app.recouvrement import (
    PHASE_LABELS,
    ensure_relance_backlog,
    jours_retard,
    montant_du,
    phase_courante,
    prochaine_echeance,
)


@dataclass
class ContratContext:
    contrat: Contrat
    demande: Demande
    paiements: list[Paiement]
    jours_retard: int
    phase: int
    montant_du: int
    prochaine: Paiement | None
    derniere_action: Relance | None


def build_context(
    *, session: Session, contrat: Contrat, today: date | None = None, reconcile: bool = True
) -> ContratContext:
    demande = contrat.demande
    paiements = crud.get_paiements(session=session, contrat_id=contrat.id)
    if reconcile:
        ensure_relance_backlog(session=session, contrat=contrat, paiements=paiements, today=today)

    relances = crud.get_relances(session=session, contrat_id=contrat.id)
    jours = jours_retard(paiements, today)
    return ContratContext(
        contrat=contrat,
        demande=demande,
        paiements=paiements,
        jours_retard=jours,
        phase=phase_courante(jours),
        montant_du=montant_du(paiements, today),
        prochaine=prochaine_echeance(paiements, today),
        derniere_action=relances[0] if relances else None,
    )


def dossier_reference(demande: Demande) -> str:
    year = demande.created_at.year if demande.created_at else date.today().year
    return f"PCP-{year}-{str(demande.id)[:4].upper()}"


def client_nom(demande: Demande) -> str:
    return f"{demande.prenom} {demande.nom}".strip()


def vehicule_label(demande: Demande) -> str:
    parts = [demande.marque, demande.modele, str(demande.annee) if demande.annee else None]
    label = " ".join(p for p in parts if p)
    return label or "—"


def latest_cutoff_at(relances: list[Relance]) -> datetime | None:
    """
    Horodatage du dernier coupe-moteur — les relances sont attendues triées
    par `created_at` décroissant (voir crud.get_relances). Si le contrat est
    actuellement coupé, cette entrée existe forcément (une réactivation
    aurait remis `cutoff_active` à False).
    """
    for r in relances:
        if r.canal.value == "coupe_moteur":
            return r.created_at
    return None


def relance_created_by_name(session: Session, relance: Relance | None) -> str | None:
    if relance is None or relance.created_by is None:
        return "Recover Bot" if relance and relance.origine.value == "auto" else None
    from app.models import User

    user = session.get(User, relance.created_by)
    return (user.full_name or user.email) if user else None


def to_relance_public(session: Session, relance: Relance) -> dict:
    return {
        "id": relance.id,
        "contrat_id": relance.contrat_id,
        "canal": relance.canal,
        "origine": relance.origine,
        "note": relance.note,
        "created_by_name": relance_created_by_name(session, relance),
        "created_at": relance.created_at,
    }


def to_echeance_public(paiement: Paiement) -> EcheancePublic:
    today = date.today()
    if paiement.paid_at is not None:
        statut = "paye"
    elif paiement.date_echeance <= today:
        statut = "retard"
    else:
        statut = "attendu"
    return EcheancePublic(
        id=paiement.id,
        contrat_id=paiement.contrat_id,
        index=paiement.index,
        date_echeance=paiement.date_echeance,
        montant=paiement.montant,
        statut=statut,
        paid_at=paiement.paid_at,
        mode_paiement=paiement.mode_paiement,
    )


def to_dossier_public(session: Session, contrat: Contrat) -> ContratDossierPublic:
    ctx = build_context(session=session, contrat=contrat)
    return ContratDossierPublic(
        id=ctx.contrat.id,
        demande_id=ctx.demande.id,
        reference=dossier_reference(ctx.demande),
        client_nom=client_nom(ctx.demande),
        client_telephone=ctx.demande.owner.phone if ctx.demande.owner else None,
        vehicule=vehicule_label(ctx.demande),
        montant_finance=ctx.demande.prix_vehicule,
        duree_mois=ctx.demande.duree_mois,
        mensualite=ctx.demande.mensualite,
        plate=ctx.contrat.plate,
        cutoff_active=ctx.contrat.cutoff_active,
        jours_retard=ctx.jours_retard,
        phase=ctx.phase,
        phase_label=PHASE_LABELS[ctx.phase],
        montant_du=ctx.montant_du,
        derniere_action=to_relance_public(session, ctx.derniere_action)
        if ctx.derniere_action
        else None,
        prochaine_echeance=to_echeance_public(ctx.prochaine) if ctx.prochaine else None,
    )


def _vehicule_fields(session: Session, contrat: Contrat) -> dict:
    ctx = build_context(session=session, contrat=contrat)
    relances = crud.get_relances(session=session, contrat_id=contrat.id)
    cutoff_since = latest_cutoff_at(relances) if ctx.contrat.cutoff_active else None
    now = datetime.now(timezone.utc)

    telemetry = gps_simulator.simulate_telemetry(
        contrat.id, now=now, cutoff_active=ctx.contrat.cutoff_active, cutoff_since=cutoff_since
    )
    statut = "coupe" if ctx.contrat.cutoff_active else ("alerte" if ctx.jours_retard > 0 else "normal")
    derniere_maj = cutoff_since if ctx.contrat.cutoff_active and cutoff_since else now

    return {
        "id": contrat.id,
        "demande_id": ctx.demande.id,
        "plate": contrat.plate,
        "client_nom": client_nom(ctx.demande),
        "vehicule": vehicule_label(ctx.demande),
        "position": PositionPublic(lat=telemetry.lat, lon=telemetry.lon, lieu=telemetry.lieu),
        "vitesse": telemetry.vitesse,
        "moteur": telemetry.moteur,
        "statut": statut,
        "cutoff_active": ctx.contrat.cutoff_active,
        "derniere_maj": derniere_maj,
    }


def to_vehicule_public(session: Session, contrat: Contrat) -> VehiculePublic:
    return VehiculePublic(**_vehicule_fields(session, contrat))


def to_vehicule_detail_public(session: Session, contrat: Contrat) -> VehiculeDetailPublic:
    fields = _vehicule_fields(session, contrat)
    stats = gps_simulator.simulate_stats_du_jour(contrat.id, datetime.now(timezone.utc))
    return VehiculeDetailPublic(
        **fields,
        gps_device_id=contrat.gps_device_id,
        stats_du_jour=StatsDuJourPublic(**stats),
    )
