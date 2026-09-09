"""
Rule-based credit scoring ("Score IA").

There is no ML model and no external data connectors (Mobile Money,
BCEAO, Open Banking) wired up yet. The score is computed deterministically
from what actually exists on the demande: declared income, seniority,
debt ratio, and how complete/verified the supporting documents are.

Two axes from the product spec — "Comportement Mobile Money" and
"Antécédents BCEAO" — have no data source at all today, so they are
marked `disponible=False` and excluded from the total/max instead of
being guessed. The score's denominator (`max`) reflects only the axes
that are actually connected, so it never silently overstates certainty.
"""

from app.models import Demande

SEUIL_ENDETTEMENT = 0.40  # seuil PCP
ANCIENNETE_MIN_ANNEES = 1  # 12 mois


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def _revenu_stabilite_emploi(demande: Demande) -> int:
    """/200 — adéquation du revenu déclaré + ancienneté professionnelle."""
    revenu_score = (
        _clamp(demande.revenu_mensuel / 500_000 * 100) if demande.revenu_mensuel else 0
    )
    stabilite_score = (
        _clamp(demande.anciennete_annees / 7 * 100) if demande.anciennete_annees else 0
    )
    return round(revenu_score + stabilite_score)


def _ratio_endettement(demande: Demande) -> int:
    """/200 — mensualité rapportée au revenu déclaré (seuil PCP 40 %)."""
    if not demande.revenu_mensuel or not demande.mensualite:
        return 0
    ratio = demande.mensualite / demande.revenu_mensuel
    if ratio <= 0.30:
        return 200
    if ratio >= 0.60:
        return 0
    return round(_clamp(200 - (ratio - 0.30) / (0.60 - 0.30) * 200, 0, 200))


AXES = [
    {
        "key": "revenu_stabilite",
        "label": "Revenu / stabilité emploi",
        "max": 200,
        "compute": _revenu_stabilite_emploi,
    },
    {
        "key": "ratio_endettement",
        "label": "Ratio d'endettement",
        "max": 200,
        "compute": _ratio_endettement,
    },
    {
        "key": "mobile_money",
        "label": "Comportement Mobile Money",
        "max": 200,
        "compute": None,  # aucun connecteur Mobile Money branché
    },
    {
        "key": "bceao",
        "label": "Antécédents BCEAO",
        "max": 250,
        "compute": None,  # aucune consultation centrale des risques branchée
    },
]

DOC_KEYWORDS = {
    "OCR CNI": ("cni", "passeport"),
    "OCR Bulletin de salaire": ("bulletin", "salaire"),
    "Relevé bancaire (6 mois)": ("bancaire", "relevé"),
}


def _document_fourni(demande: Demande, keywords: tuple[str, ...]) -> bool:
    for doc in demande.documents:
        type_lower = doc.type.lower()
        if doc.has_file and any(kw in type_lower for kw in keywords):
            return True
    return False


def compute_score(demande: Demande) -> dict:
    axes = []
    total = 0
    total_max = 0
    for axe in AXES:
        if axe["compute"] is None:
            axes.append(
                {
                    "key": axe["key"],
                    "label": axe["label"],
                    "valeur": None,
                    "max": axe["max"],
                    "disponible": False,
                }
            )
            continue
        valeur = axe["compute"](demande)
        axes.append(
            {
                "key": axe["key"],
                "label": axe["label"],
                "valeur": valeur,
                "max": axe["max"],
                "disponible": True,
            }
        )
        total += valeur
        total_max += axe["max"]

    pct = (total / total_max * 100) if total_max else 0
    if pct >= 75:
        decision = "approuve_auto"
    elif pct >= 50:
        decision = "analyse_renforcee"
    else:
        decision = "defavorable"

    # --- Signaux détectés par l'IA (uniquement sur des données réelles) ---
    signaux = []
    if demande.revenu_mensuel and demande.mensualite:
        ratio = demande.mensualite / demande.revenu_mensuel
        if ratio < SEUIL_ENDETTEMENT:
            signaux.append(
                {
                    "type": "ok",
                    "label": f"Taux d'endettement : {ratio * 100:.1f} % < {SEUIL_ENDETTEMENT * 100:.0f} % (seuil PCP)",
                }
            )
        else:
            signaux.append(
                {
                    "type": "warning",
                    "label": f"Taux d'endettement : {ratio * 100:.1f} % ≥ {SEUIL_ENDETTEMENT * 100:.0f} % (seuil PCP)",
                }
            )
    else:
        signaux.append({"type": "warning", "label": "Revenu ou mensualité non renseigné(e)"})

    if demande.anciennete_annees:
        if demande.anciennete_annees >= ANCIENNETE_MIN_ANNEES:
            signaux.append(
                {
                    "type": "ok",
                    "label": f"Ancienneté poste : {demande.anciennete_annees} an(s) (minimum PCP = 12 mois ✓)",
                }
            )
        else:
            signaux.append(
                {
                    "type": "warning",
                    "label": f"Ancienneté poste : {demande.anciennete_annees} an(s) (minimum PCP = 12 mois)",
                }
            )
    else:
        signaux.append({"type": "warning", "label": "Ancienneté professionnelle non renseignée"})

    nb_docs = len(demande.documents)
    nb_fournis = sum(1 for d in demande.documents if d.has_file)
    if nb_docs:
        if nb_fournis == nb_docs:
            signaux.append(
                {"type": "ok", "label": f"Dossier documentaire complet ({nb_fournis}/{nb_docs})"}
            )
        else:
            signaux.append(
                {
                    "type": "warning",
                    "label": f"Dossier documentaire incomplet ({nb_fournis}/{nb_docs} fournis)",
                }
            )
        nb_ocr = sum(1 for d in demande.documents if d.has_file and d.ocr)
        if nb_fournis and nb_ocr == nb_fournis:
            signaux.append({"type": "ok", "label": f"Vérification OCR validée sur les {nb_fournis} document(s) fourni(s)"})
        elif nb_fournis:
            signaux.append(
                {
                    "type": "warning",
                    "label": f"Vérification OCR incomplète ({nb_ocr}/{nb_fournis} documents fournis validés)",
                }
            )
    else:
        signaux.append({"type": "warning", "label": "Aucun document associé au dossier"})

    signaux.append(
        {"type": "unavailable", "label": "Comportement Mobile Money : connecteur non activé"}
    )
    signaux.append(
        {"type": "unavailable", "label": "Antécédents BCEAO : consultation non activée"}
    )

    # --- Sources de données utilisées ---
    sources = [
        {"label": label, "disponible": _document_fourni(demande, kw)}
        for label, kw in DOC_KEYWORDS.items()
    ]
    sources.append({"label": "Consultation centrale des risques BCEAO", "disponible": False})
    sources.append({"label": "Open Banking", "disponible": False})

    return {
        "total": total,
        "max": total_max,
        "decision": decision,
        "axes": axes,
        "signaux": signaux,
        "sources": sources,
    }
