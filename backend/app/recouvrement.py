"""
Recover Bot — calcul du retard réel et rattrapage des relances automatiques.

Il n'y a pas de tâche planifiée (cron) dans ce projet. À la place, l'état du
Recover Bot avance tout seul avec le temps réel : à chaque lecture des
dossiers en retard (`GET /recouvrement/dossiers`), `ensure_relance_backlog`
compare le retard actuel d'un contrat aux seuils de phase et journalise,
rétroactivement, les relances qui auraient dû partir depuis la dernière
consultation — de façon idempotente (une phase n'est jamais loguée deux fois
pour le même épisode de retard).

Un "épisode de retard" est ancré sur la date d'échéance de la plus ancienne
mensualité impayée. Tant que cette échéance n'est pas payée, c'est le même
épisode : les phases déjà déclenchées ne repartent pas. Dès qu'elle est
payée, l'épisode suivant (s'il y en a un) repart de zéro.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlmodel import Session, select

from app.models import CanalRelance, Contrat, OrigineRelance, Paiement, Relance


class Phase:
    def __init__(self, index: int, canal: CanalRelance, label: str, seuil_jours: int):
        self.index = index
        self.canal = canal
        self.label = label
        self.seuil_jours = seuil_jours


PHASES: list[Phase] = [
    Phase(1, CanalRelance.sms, "SMS automatique", 3),
    Phase(2, CanalRelance.whatsapp, "WhatsApp", 7),
    Phase(3, CanalRelance.appel, "Appel agent", 15),
    Phase(4, CanalRelance.coupe_moteur, "Coupe-moteur", 30),
]

PHASE_LABELS: dict[int, str] = {0: "À jour", **{p.index: p.label for p in PHASES}}


def _today(today: date | None) -> date:
    return today or datetime.now(timezone.utc).date()


def oldest_unpaid(paiements: list[Paiement], today: date | None = None) -> Paiement | None:
    """La plus ancienne échéance en retard (impayée, date dépassée), s'il y en a une."""
    today = _today(today)
    en_retard = [p for p in paiements if p.paid_at is None and p.date_echeance <= today]
    if not en_retard:
        return None
    return min(en_retard, key=lambda p: p.date_echeance)


def jours_retard(paiements: list[Paiement], today: date | None = None) -> int:
    today = _today(today)
    oldest = oldest_unpaid(paiements, today)
    if not oldest:
        return 0
    return (today - oldest.date_echeance).days


def montant_du(paiements: list[Paiement], today: date | None = None) -> int:
    today = _today(today)
    return sum(
        p.montant for p in paiements if p.paid_at is None and p.date_echeance <= today
    )


def phase_courante(jours: int) -> int:
    phase = 0
    for p in PHASES:
        if jours >= p.seuil_jours:
            phase = p.index
    return phase


def prochaine_echeance(paiements: list[Paiement], today: date | None = None) -> Paiement | None:
    today = _today(today)
    a_venir = [p for p in paiements if p.paid_at is None]
    if not a_venir:
        return None
    return min(a_venir, key=lambda p: p.date_echeance)


def ensure_relance_backlog(
    *, session: Session, contrat: Contrat, paiements: list[Paiement], today: date | None = None
) -> None:
    """
    Rattrape, de façon idempotente, les relances automatiques dues pour
    l'épisode de retard en cours. Active le coupe-moteur au passage de la
    phase 4 (une seule fois par épisode — une réactivation manuelle n'est
    pas re-coupée tant qu'un nouvel épisode de retard n'est pas ouvert).
    """
    today = _today(today)
    oldest = oldest_unpaid(paiements, today)
    if not oldest:
        return

    episode_start_dt = datetime.combine(oldest.date_echeance, time.min, tzinfo=timezone.utc)
    jours = (today - oldest.date_echeance).days
    dirty = False

    for phase in PHASES:
        if jours < phase.seuil_jours:
            continue
        already = session.exec(
            select(Relance).where(
                Relance.contrat_id == contrat.id,
                Relance.canal == phase.canal,
                Relance.created_at >= episode_start_dt,
            )
        ).first()
        if already:
            continue

        triggered_at = episode_start_dt + timedelta(days=phase.seuil_jours)
        session.add(
            Relance(
                contrat_id=contrat.id,
                canal=phase.canal,
                origine=OrigineRelance.auto,
                note=f"Déclenché automatiquement — {phase.label} (retard {phase.seuil_jours}+ jours)",
                created_at=triggered_at,
            )
        )
        if phase.canal == CanalRelance.coupe_moteur:
            contrat.cutoff_active = True
            session.add(contrat)
        dirty = True

    if dirty:
        session.commit()
