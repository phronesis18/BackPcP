import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from app import crud
from app.api.deps import CurrentUser, SessionDep
from app.contrats_service import build_context
from app.models import (
    Distribution,
    DistributionCreate,
    DistributionPublic,
    DistributionsPublic,
    DistributionUpdate,
    EvolutionEncoursPoint,
    InvestissementPerformancePublic,
    RepartitionMarque,
    StatutDistribution,
)

router = APIRouter(prefix="/investissements", tags=["investissements"])

_MOIS_FR = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]


def _require_investisseur_ou_back_office(current_user: CurrentUser) -> None:
    if not (current_user.is_superuser or current_user.is_admin or current_user.is_investisseur):
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _require_back_office(current_user: CurrentUser) -> None:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _shift_month(key: tuple[int, int], delta: int) -> tuple[int, int]:
    y, m = key
    index = (y * 12 + (m - 1)) + delta
    return (index // 12, index % 12 + 1)


@router.get("/performance", response_model=InvestissementPerformancePublic)
def read_performance(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    KPIs du fonds calculés depuis les vrais contrats signés — pas de TRI ni
    de rendement inventés : encours, taux d'impayés, répartition et TEG moyen
    reflètent l'état réel du portefeuille.
    """
    _require_investisseur_ou_back_office(current_user)
    contrats = crud.get_contrats(session=session)

    encours_total = 0
    contrats_actifs = 0
    en_retard = 0
    teg_pondere_somme = 0.0
    poids_total = 0
    marque_counts: dict[str, int] = {}
    mois_cumule: dict[tuple[int, int], int] = {}

    today = date.today()
    for contrat in contrats:
        ctx = build_context(session=session, contrat=contrat, today=today, reconcile=False)
        restant = sum(p.montant for p in ctx.paiements if p.paid_at is None)
        prix = ctx.demande.prix_vehicule or 0

        # Le portefeuille "actif" — encours, répartition, TEG et impayés —
        # ne porte que sur les contrats encore en cours de remboursement.
        # Un contrat soldé ne pèse plus sur la performance courante du fonds.
        if restant > 0:
            contrats_actifs += 1
            encours_total += restant
            if ctx.jours_retard > 0:
                en_retard += 1
            if ctx.demande.taux_teg is not None and prix:
                teg_pondere_somme += ctx.demande.taux_teg * prix
                poids_total += prix
            marque = ctx.demande.marque or "Autres"
            marque_counts[marque] = marque_counts.get(marque, 0) + 1

        # L'évolution du capital engagé, elle, reste cumulative dans le temps
        # (elle raconte la croissance du fonds, pas son état courant).
        signed = contrat.signed_at.date()
        key = _month_key(signed)
        mois_cumule[key] = mois_cumule.get(key, 0) + prix

    teg_moyen = round(teg_pondere_somme / poids_total, 2) if poids_total else 0.0
    taux_impayes = round((en_retard / contrats_actifs) * 100, 1) if contrats_actifs else 0.0

    # Évolution du capital engagé cumulé sur les 6 derniers mois calendaires.
    current_key = _month_key(today)
    months = [_shift_month(current_key, -i) for i in range(5, -1, -1)]
    cumule = sum(v for k, v in mois_cumule.items() if k < months[0])
    evolution: list[EvolutionEncoursPoint] = []
    for y, m in months:
        cumule += mois_cumule.get((y, m), 0)
        evolution.append(EvolutionEncoursPoint(mois=_MOIS_FR[m - 1], encours=cumule))

    total_marques = sum(marque_counts.values()) or 1
    repartition = [
        RepartitionMarque(marque=k, count=v, pct=round(v / total_marques * 100, 1))
        for k, v in sorted(marque_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    capital_total = crud.get_investisseurs_total_capital(session=session)
    mon_investissement = current_user.capital_investi if current_user.is_investisseur else None
    part_pct = (
        round(mon_investissement / capital_total * 100, 2)
        if mon_investissement and capital_total
        else None
    )

    distributions = crud.get_distributions(session=session)
    versees = [d for d in distributions if d.statut == StatutDistribution.versee]
    total_verse = sum(d.montant_total for d in versees)
    mes_dividendes = (
        round(total_verse * (mon_investissement / capital_total))
        if mon_investissement and capital_total
        else None
    )
    a_venir = [d for d in distributions if d.statut == StatutDistribution.prevue]
    prochain = min(a_venir, key=lambda d: d.date_versement) if a_venir else None

    return InvestissementPerformancePublic(
        encours_total=encours_total,
        contrats_actifs=contrats_actifs,
        taux_impayes_pct=taux_impayes,
        teg_moyen_pondere=teg_moyen,
        evolution=evolution,
        repartition_marque=repartition,
        capital_total_investisseurs=capital_total,
        mon_investissement=mon_investissement,
        part_du_fonds_pct=part_pct,
        mes_dividendes_recus=mes_dividendes,
        prochain_versement=DistributionPublic.model_validate(prochain) if prochain else None,
    )


@router.get("/distributions", response_model=DistributionsPublic)
def read_distributions(session: SessionDep, current_user: CurrentUser) -> Any:
    _require_investisseur_ou_back_office(current_user)
    distributions = crud.get_distributions(session=session)
    return DistributionsPublic(data=distributions, count=len(distributions))


@router.post("/distributions", response_model=DistributionPublic, status_code=201)
def create_distribution_route(
    session: SessionDep, current_user: CurrentUser, distribution_in: DistributionCreate
) -> Any:
    _require_back_office(current_user)
    return crud.create_distribution(session=session, distribution_in=distribution_in)


@router.patch("/distributions/{distribution_id}", response_model=DistributionPublic)
def update_distribution_route(
    session: SessionDep,
    current_user: CurrentUser,
    distribution_id: uuid.UUID,
    distribution_in: DistributionUpdate,
) -> Any:
    _require_back_office(current_user)
    db_distribution = session.get(Distribution, distribution_id)
    if not db_distribution:
        raise HTTPException(status_code=404, detail="Distribution introuvable")
    return crud.update_distribution(
        session=session, db_distribution=db_distribution, distribution_in=distribution_in
    )
