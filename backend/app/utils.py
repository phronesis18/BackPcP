import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import emails  # type: ignore[import-untyped]
import jwt
from jinja2 import Template
from jwt.exceptions import InvalidTokenError

from app.core import security
from app.core.config import settings
from app.models import StatutDemande

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    template_str = (
        Path(__file__).parent / "email-templates" / "build" / template_name
    ).read_text()
    html_content = Template(template_str).render(context)
    return html_content


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    assert settings.emails_enabled, "no provided configuration for email variables"
    message = emails.Message(
        subject=subject,
        html=html_content,
        mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
    )
    smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    if settings.SMTP_TLS:
        smtp_options["tls"] = True
    elif settings.SMTP_SSL:
        smtp_options["ssl"] = True
    if settings.SMTP_USER:
        smtp_options["user"] = settings.SMTP_USER
    if settings.SMTP_PASSWORD:
        smtp_options["password"] = settings.SMTP_PASSWORD
    response = message.send(to=email_to, smtp=smtp_options)
    # `emails` never raises on its own for a connection/auth failure — it just
    # returns a response with status_code=None, so a down SMTP server would
    # otherwise look identical to a successful send. Surface it explicitly.
    response.raise_if_needed()
    logger.info(f"send email result: {response}")


def generate_test_email(email_to: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Test email"
    html_content = render_email_template(
        template_name="test_email.html",
        context={"project_name": settings.PROJECT_NAME, "email": email_to},
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_reset_password_email(email_to: str, email: str, token: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Password recovery for user {email}"
    link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"
    html_content = render_email_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_new_account_email(
    email_to: str, username: str, password: str
) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - New account for user {username}"
    html_content = render_email_template(
        template_name="new_account.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "password": password,
            "email": email_to,
            "link": settings.FRONTEND_HOST,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


# Contenu par statut pour l'email envoyé au client quand sa demande de
# crédit change d'état — un seul template générique (demande_statut.html),
# le texte et la couleur varient selon le statut atteint.
_DEMANDE_STATUT_CONTENT: dict[StatutDemande, dict[str, str]] = {
    StatutDemande.validee: {
        "label": "Dossier validé",
        "color": "#16a34a",
        "message": (
            "Bonne nouvelle {prenom} ! Après étude, votre dossier de financement pour "
            "{vehicule} a été validé. Il ne reste qu'une étape : connectez-vous à votre "
            "espace client pour signer électroniquement votre contrat et démarrer votre "
            "financement."
        ),
    },
    StatutDemande.rejectee: {
        "label": "Dossier non retenu",
        "color": "#dc2626",
        "message": (
            "Bonjour {prenom}, après étude, nous ne sommes malheureusement pas en mesure "
            "de donner une suite favorable à votre demande de financement pour {vehicule}. "
            "Vous pouvez déposer une nouvelle demande à tout moment depuis votre espace "
            "client."
        ),
    },
    StatutDemande.complement_demande: {
        "label": "Complément de dossier requis",
        "color": "#d97706",
        "message": (
            "Bonjour {prenom}, il manque au moins un élément pour poursuivre l'étude de "
            "votre dossier de financement pour {vehicule}. Merci de vous connecter à "
            "votre espace client pour consulter les documents à fournir et ne pas "
            "retarder la décision."
        ),
    },
}


def generate_demande_statut_email(
    *,
    email_to: str,
    client_prenom: str,
    dossier_ref: str,
    vehicule_label: str,
    statut: StatutDemande,
) -> EmailData | None:
    """
    `None` when `statut` isn't one of the three states a client is notified
    about (soumise/en_etude/signee don't get an email — signee already has
    its own confirmation flow via contract signing).
    """
    content = _DEMANDE_STATUT_CONTENT.get(statut)
    if not content:
        return None
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - {content['label']} ({dossier_ref})"
    html_content = render_email_template(
        template_name="demande_statut.html",
        context={
            "project_name": project_name,
            "statut_label": content["label"],
            "statut_color": content["color"],
            "dossier_ref": dossier_ref,
            "vehicule_label": vehicule_label,
            "message": content["message"].format(prenom=client_prenom, vehicule=vehicule_label),
            "link": settings.FRONTEND_HOST,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_password_reset_token(email: str) -> str:
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email},
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return str(decoded_token["sub"])
    except InvalidTokenError:
        return None
