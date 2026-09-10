"""
Recouvrement ("collections") — computed purely from real data: the payment
schedule (Echeance) generated at contract signing, and the manual action log
(ActionRecouvrement) an admin fills in by hand. There is no SMS/WhatsApp/call
provider and no GPS/immobilizer telemetry connected to this app, so
`derniere_action` and `moteur_coupe` only ever reflect what an admin actually
recorded — never an automatic send or a real hardware read.

The recommended next step (`prochaine_action_suggeree`) mirrors the exact
J+3/J+7/J+15/J+30 policy described in the credit contract itself (see
Article 5 in lib/demandes.ts::buildContratContenu on the frontend), so the
UI and the legal text never contradict each other.
"""

from datetime import date, timedelta

from app.models import ActionRecouvrement, Echeance

SEUIL_J16 = 16
SEUIL_COUPE_MOTEUR = 30

PALIERS = [
    (3, "Envoyer un SMS de relance"),
    (7, "Envoyer un message WhatsApp"),
    (15, "Appeler le client"),
    (30, "Couper le moteur à distance"),
]


def _phase(jours_retard: int) -> str:
    if jours_retard >= SEUIL_COUPE_MOTEUR:
        return "coupe_moteur"
    if jours_retard >= SEUIL_J16:
        return "j16_30"
    return "j1_15"


def _moteur_coupe(actions: list[ActionRecouvrement]) -> bool:
    """`actions` must already be sorted most-recent-first."""
    for action in actions:
        if action.type == "coupe_moteur":
            return True
        if action.type == "reactivation":
            return False
    return False


def compute_recouvrement(
    echeances: list[Echeance], actions: list[ActionRecouvrement]
) -> dict:
    """`actions` must already be sorted most-recent-first."""
    today = date.today()
    impayees_dues = [e for e in echeances if not e.payee and e.date_echeance < today]
    moteur_coupe = _moteur_coupe(actions)
    derniere_action = actions[0] if actions else None

    if not impayees_dues:
        return {
            "en_retard": False,
            "jours_retard": 0,
            "montant_du": 0,
            "phase": None,
            "moteur_coupe": moteur_coupe,
            "derniere_action": derniere_action,
            "prochaine_action_suggeree": None,
            "prochaine_action_date": None,
        }

    premiere = min(impayees_dues, key=lambda e: e.date_echeance)
    jours_retard = (today - premiere.date_echeance).days
    montant_du = sum(e.montant for e in impayees_dues)

    prochaine_label = None
    prochaine_date = None
    for seuil, label in PALIERS:
        if jours_retard < seuil:
            prochaine_label = label
            prochaine_date = premiere.date_echeance + timedelta(days=seuil)
            break

    return {
        "en_retard": True,
        "jours_retard": jours_retard,
        "montant_du": montant_du,
        "phase": _phase(jours_retard),
        "moteur_coupe": moteur_coupe,
        "derniere_action": derniere_action,
        "prochaine_action_suggeree": prochaine_label,
        "prochaine_action_date": prochaine_date,
    }


def flotte_statut(recouvrement: dict) -> str:
    """
    Fleet Monitor's status pill for a vehicle — derived from the exact same
    recouvrement computation as the collections module, so the two screens
    can never disagree about whether a car's engine is cut.
    """
    if recouvrement["moteur_coupe"]:
        return "coupe_moteur"
    if recouvrement["en_retard"]:
        return "alerte"
    return "normal"
