"""
Extraction OCR des documents (CNI, bulletin de salaire) via Claude Vision.

Il n'y a aucun connecteur Mobile Money/BCEAO/Open Banking dans cette app —
ceci ne fait que lire les champs visibles sur un document réellement
uploadé et les comparer à ce que le client a déclaré dans le formulaire.
Un écart ne remplace jamais la valeur déclarée ni ne change le score : il
est seulement remonté à l'admin pour qu'un humain tranche (voir
ActionRecouvrementDialog pour le même principe côté recouvrement — jamais
d'automatisation silencieuse sur des décisions qui engagent le client).
"""

import base64
import json

import anthropic

from app.core.config import settings
from app.models import Demande, Document

MODEL = "claude-sonnet-5"

# Tolérance avant de signaler un écart de revenu — une photo de bulletin
# légèrement flou ou un primes/indemnités variables ne doivent pas déclencher
# une fausse alerte pour quelques milliers de FCFA.
TOLERANCE_REVENU = 0.10

SCHEMAS: dict[str, dict] = {
    "cni": {
        "champs": ["nom", "prenom", "date_naissance", "cni_number"],
        "instructions": (
            "Ceci est une pièce d'identité béninoise (CNI ou passeport). "
            "Lis-la et extrait le nom de famille, le prénom, la date de "
            "naissance (au format lisible tel qu'écrit sur le document) et "
            "le numéro de la pièce."
        ),
    },
    "bulletin_salaire": {
        "champs": ["employeur", "revenu_net"],
        "instructions": (
            "Ceci est un bulletin de salaire. Lis-le et extrait le nom de "
            "l'employeur et le salaire net mensuel en FCFA (uniquement les "
            "chiffres, sans espace ni devise, ex. 250000)."
        ),
    },
}

CNI_KEYWORDS = ("cni", "passeport")
BULLETIN_KEYWORDS = ("bulletin", "salaire")


class OcrError(Exception):
    pass


def categorie_document(document: Document) -> str | None:
    type_lower = document.type.lower()
    if any(kw in type_lower for kw in CNI_KEYWORDS):
        return "cni"
    if any(kw in type_lower for kw in BULLETIN_KEYWORDS):
        return "bulletin_salaire"
    return None


def _content_block(document: Document) -> dict:
    data = base64.b64encode(document.fichier).decode()
    if document.content_type == "application/pdf":
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": data},
        }
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": document.content_type or "image/jpeg",
            "data": data,
        },
    }


def _normalise_texte(valeur: str) -> str:
    return " ".join(valeur.strip().upper().split())


def _texte_vers_entier(valeur: str) -> int | None:
    chiffres = "".join(c for c in valeur if c.isdigit())
    return int(chiffres) if chiffres else None


def _comparer(categorie: str, champs: dict, demande: Demande) -> list[dict]:
    ecarts = []
    if categorie == "cni":
        for cle, champ_demande, label in [
            ("nom", "nom", "Nom"),
            ("prenom", "prenom", "Prénom"),
            ("cni_number", "cni_number", "Numéro CNI"),
        ]:
            extrait = str(champs.get(cle) or "").strip()
            declare = str(getattr(demande, champ_demande) or "")
            if extrait and declare and _normalise_texte(extrait) != _normalise_texte(declare):
                ecarts.append(
                    {"champ": label, "valeur_declaree": declare, "valeur_extraite": extrait}
                )
    elif categorie == "bulletin_salaire":
        revenu_extrait = _texte_vers_entier(str(champs.get("revenu_net") or ""))
        if revenu_extrait and demande.revenu_mensuel:
            ecart_pct = abs(revenu_extrait - demande.revenu_mensuel) / demande.revenu_mensuel
            if ecart_pct > TOLERANCE_REVENU:
                ecarts.append(
                    {
                        "champ": "Revenu mensuel",
                        "valeur_declaree": f"{demande.revenu_mensuel} FCFA",
                        "valeur_extraite": f"{revenu_extrait} FCFA",
                    }
                )
        employeur_extrait = str(champs.get("employeur") or "").strip()
        if (
            employeur_extrait
            and demande.employeur
            and _normalise_texte(employeur_extrait) != _normalise_texte(demande.employeur)
        ):
            ecarts.append(
                {
                    "champ": "Employeur",
                    "valeur_declaree": demande.employeur,
                    "valeur_extraite": employeur_extrait,
                }
            )
    return ecarts


def analyser_document(document: Document, demande: Demande) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        raise OcrError("Aucune clé ANTHROPIC_API_KEY n'est configurée côté serveur.")
    if not document.fichier:
        raise OcrError("Ce document n'a aucun fichier associé.")
    categorie = categorie_document(document)
    if categorie is None:
        raise OcrError(
            "Analyse OCR non prise en charge pour ce type de document "
            "(CNI/passeport ou bulletin de salaire uniquement)."
        )

    schema = SCHEMAS[categorie]
    prompt = (
        f"{schema['instructions']}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON (aucun texte avant ou après) "
        f"contenant exactement ces clés : {', '.join(schema['champs'])}. "
        'Utilise une chaîne vide "" pour un champ illisible ou absent.'
    )

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [_content_block(document), {"type": "text", "text": prompt}],
                }
            ],
        )
    except anthropic.APIError as exc:
        raise OcrError(f"Échec de l'appel au service d'extraction : {exc}") from exc

    raw_text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    try:
        champs = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise OcrError("Réponse d'extraction illisible — réessayez.") from exc

    if not isinstance(champs, dict):
        raise OcrError("Réponse d'extraction invalide — réessayez.")

    return {
        "categorie": categorie,
        "champs": champs,
        "ecarts": _comparer(categorie, champs, demande),
    }
