import calendar
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlmodel import Session, col, func, select

from app.core.security import get_password_hash, verify_password
from app.models import (
    ActionRecouvrement,
    ActionRecouvrementCreate,
    ChatMessage,
    ChatMessageCreate,
    Contrat,
    ContratCreate,
    Demande,
    DemandeCreate,
    Distribution,
    DistributionCreate,
    DistributionUpdate,
    Document,
    DocumentCreate,
    Echeance,
    InvestisseurProfil,
    InvestisseurProfilUpdate,
    Marque,
    MarqueCreate,
    MarqueUpdate,
    Modele,
    ModeleAnnee,
    ModeleAnneeCreate,
    ModeleAnneeUpdate,
    ModeleCreate,
    ModeleUpdate,
    MessagerieConversationPublic,
    ParametresFinanciers,
    ParametresFinanciersUpdate,
    StatutDemande,
    StatutDistribution,
    User,
    UserCreate,
    UserMessage,
    UserMessageCreate,
    UserUpdate,
    VehiculeFlotte,
    VehiculeFlotteUpdate,
    Vendeur,
    VendeurCreate,
    VendeurUpdate,
    get_datetime_utc,
)
from app.recouvrement import compute_recouvrement


def create_user(
    *, session: Session, user_create: UserCreate, must_change_password: bool = False
) -> User:
    db_obj = User.model_validate(
        user_create,
        update={
            "hashed_password": get_password_hash(user_create.password),
            "must_change_password": must_change_password,
        },
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


def get_user_by_phone(*, session: Session, phone: str) -> User | None:
    statement = select(User).where(User.phone == phone)
    session_user = session.exec(statement).first()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user



def create_demande(
    *, session: Session, demande_in: DemandeCreate, owner_id: uuid.UUID
) -> Demande:
    demande_data = demande_in.model_dump(exclude={"documents"})
    demande = Demande.model_validate(demande_data, update={"owner_id": owner_id})
    session.add(demande)
    session.commit()
    session.refresh(demande)

    for doc_in in demande_in.documents or []:
        document = Document.model_validate(doc_in, update={"demande_id": demande.id})
        session.add(document)
    if demande_in.documents:
        session.commit()
        session.refresh(demande)
    return demande


def get_demandes(
    *,
    session: Session,
    owner_id: uuid.UUID | None = None,
    statut: StatutDemande | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[Demande], int]:
    statement = select(Demande)
    count_statement = select(func.count()).select_from(Demande)
    if owner_id is not None:
        statement = statement.where(Demande.owner_id == owner_id)
        count_statement = count_statement.where(Demande.owner_id == owner_id)
    if statut is not None:
        statement = statement.where(Demande.statut == statut)
        count_statement = count_statement.where(Demande.statut == statut)
    else:
        # Les brouillons ne sont visibles que si on les demande explicitement.
        statement = statement.where(Demande.statut != StatutDemande.brouillon)
        count_statement = count_statement.where(
            Demande.statut != StatutDemande.brouillon
        )

    count = session.exec(count_statement).one()
    demandes = (
        session.exec(
            statement.order_by(col(Demande.created_at).desc())
            .offset(skip)
            .limit(limit)
        ).all()
    )
    return list(demandes), count


def get_contrat(*, session: Session, demande_id: uuid.UUID) -> Contrat | None:
    statement = select(Contrat).where(Contrat.demande_id == demande_id)
    return session.exec(statement).first()


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def create_contrat(
    *, session: Session, demande_id: uuid.UUID, contrat_in: ContratCreate
) -> Contrat:
    contrat = Contrat(demande_id=demande_id, **contrat_in.model_dump())
    session.add(contrat)
    demande = session.get(Demande, demande_id)
    if demande:
        demande.statut = StatutDemande.signee
        session.add(demande)
    session.commit()
    session.refresh(contrat)
    # Les remboursements ne sont dus qu'à compter de la signature — c'est le
    # seul moment réel qui justifie de générer l'échéancier.
    if demande and demande.mensualite and demande.duree_mois:
        create_echeances(
            session=session,
            demande_id=demande_id,
            duree_mois=demande.duree_mois,
            mensualite=demande.mensualite,
            depart=contrat.signed_at.date(),
        )
    # Un véhicule financé entre dans le suivi de flotte dès la signature.
    if demande:
        get_or_create_vehicule_flotte(session=session, demande_id=demande_id)
    return contrat


# ---------------------------------------------------------------------------
# Recouvrement — échéancier réel et journal des actions de relance
# ---------------------------------------------------------------------------


def create_echeances(
    *, session: Session, demande_id: uuid.UUID, duree_mois: int, mensualite: int, depart: date
) -> list[Echeance]:
    echeances = [
        Echeance(
            demande_id=demande_id,
            numero=numero,
            date_echeance=_add_months(depart, numero),
            montant=mensualite,
        )
        for numero in range(1, duree_mois + 1)
    ]
    session.add_all(echeances)
    session.commit()
    for e in echeances:
        session.refresh(e)
    return echeances


def get_echeances(*, session: Session, demande_id: uuid.UUID) -> list[Echeance]:
    statement = (
        select(Echeance)
        .where(Echeance.demande_id == demande_id)
        .order_by(col(Echeance.numero))
    )
    return list(session.exec(statement).all())


def get_echeance(*, session: Session, echeance_id: uuid.UUID) -> Echeance | None:
    return session.get(Echeance, echeance_id)


def marquer_echeance_payee(*, session: Session, echeance: Echeance) -> Echeance:
    echeance.payee = True
    echeance.payee_le = get_datetime_utc()
    session.add(echeance)
    session.commit()
    session.refresh(echeance)
    return echeance


def annuler_echeance_payee(*, session: Session, echeance: Echeance) -> Echeance:
    echeance.payee = False
    echeance.payee_le = None
    session.add(echeance)
    session.commit()
    session.refresh(echeance)
    return echeance


def list_demandes_avec_echeancier(*, session: Session) -> list[Demande]:
    statement = (
        select(Demande)
        .join(Echeance, Echeance.demande_id == Demande.id)
        .distinct()
    )
    return list(session.exec(statement).all())


def create_action_recouvrement(
    *,
    session: Session,
    demande_id: uuid.UUID,
    created_by_id: uuid.UUID,
    action_in: ActionRecouvrementCreate,
) -> ActionRecouvrement:
    action = ActionRecouvrement(
        demande_id=demande_id, created_by_id=created_by_id, **action_in.model_dump()
    )
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


def get_actions_recouvrement(
    *, session: Session, demande_id: uuid.UUID
) -> list[ActionRecouvrement]:
    statement = (
        select(ActionRecouvrement)
        .where(ActionRecouvrement.demande_id == demande_id)
        .order_by(col(ActionRecouvrement.created_at).desc())
    )
    return list(session.exec(statement).all())


# ---------------------------------------------------------------------------
# Fleet Monitor — fiche véhicule réelle (une par contrat signé)
# ---------------------------------------------------------------------------


def get_or_create_vehicule_flotte(
    *, session: Session, demande_id: uuid.UUID
) -> VehiculeFlotte:
    vehicule = session.exec(
        select(VehiculeFlotte).where(VehiculeFlotte.demande_id == demande_id)
    ).first()
    if vehicule:
        return vehicule
    vehicule = VehiculeFlotte(demande_id=demande_id)
    session.add(vehicule)
    session.commit()
    session.refresh(vehicule)
    return vehicule


def get_vehicule_flotte(
    *, session: Session, demande_id: uuid.UUID
) -> VehiculeFlotte | None:
    return session.exec(
        select(VehiculeFlotte).where(VehiculeFlotte.demande_id == demande_id)
    ).first()


def list_vehicules_flotte(*, session: Session) -> list[VehiculeFlotte]:
    statement = select(VehiculeFlotte).order_by(col(VehiculeFlotte.created_at))
    return list(session.exec(statement).all())


def update_vehicule_flotte(
    *,
    session: Session,
    vehicule: VehiculeFlotte,
    vehicule_in: VehiculeFlotteUpdate,
    updated_by_id: uuid.UUID,
) -> VehiculeFlotte:
    update_data = vehicule_in.model_dump(exclude_unset=True)
    vehicule.sqlmodel_update(update_data)
    if "position_label" in update_data:
        vehicule.position_maj_le = get_datetime_utc()
    vehicule.updated_by_id = updated_by_id
    session.add(vehicule)
    session.commit()
    session.refresh(vehicule)
    return vehicule


def get_demande(*, session: Session, demande_id: uuid.UUID) -> Demande | None:
    return session.get(Demande, demande_id)


def create_demande_document(
    *, session: Session, demande_id: uuid.UUID, doc_in: DocumentCreate
) -> Document:
    document = Document.model_validate(doc_in, update={"demande_id": demande_id})
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def set_document_ocr_resultat(
    *, session: Session, document: Document, resultat: dict
) -> Document:
    document.ocr = True
    document.ocr_resultat = resultat
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


# ---------------------------------------------------------------------------
# Catalogue véhicules (Marque -> Modele -> ModeleAnnee)
# ---------------------------------------------------------------------------


def get_marques(*, session: Session) -> tuple[list[Marque], int]:
    statement = select(Marque).order_by(col(Marque.nom))
    marques = session.exec(statement).all()
    count = session.exec(select(func.count()).select_from(Marque)).one()
    return list(marques), count


def get_marque_by_nom(*, session: Session, nom: str) -> Marque | None:
    statement = select(Marque).where(func.lower(Marque.nom) == nom.lower())
    return session.exec(statement).first()


def create_marque(*, session: Session, marque_in: MarqueCreate) -> Marque:
    marque = Marque.model_validate(marque_in)
    session.add(marque)
    session.commit()
    session.refresh(marque)
    return marque


def update_marque(*, session: Session, db_marque: Marque, marque_in: MarqueUpdate) -> Marque:
    marque_data = marque_in.model_dump(exclude_unset=True)
    db_marque.sqlmodel_update(marque_data)
    session.add(db_marque)
    session.commit()
    session.refresh(db_marque)
    return db_marque


def get_modeles(*, session: Session, marque_id: uuid.UUID) -> tuple[list[Modele], int]:
    statement = (
        select(Modele).where(Modele.marque_id == marque_id).order_by(col(Modele.nom))
    )
    modeles = session.exec(statement).all()
    count_statement = select(func.count()).select_from(Modele).where(
        Modele.marque_id == marque_id
    )
    count = session.exec(count_statement).one()
    return list(modeles), count


def get_modele_by_nom(
    *, session: Session, marque_id: uuid.UUID, nom: str
) -> Modele | None:
    statement = select(Modele).where(
        Modele.marque_id == marque_id, func.lower(Modele.nom) == nom.lower()
    )
    return session.exec(statement).first()


def create_modele(*, session: Session, modele_in: ModeleCreate) -> Modele:
    modele = Modele.model_validate(modele_in)
    session.add(modele)
    session.commit()
    session.refresh(modele)
    return modele


def update_modele(*, session: Session, db_modele: Modele, modele_in: ModeleUpdate) -> Modele:
    modele_data = modele_in.model_dump(exclude_unset=True)
    db_modele.sqlmodel_update(modele_data)
    session.add(db_modele)
    session.commit()
    session.refresh(db_modele)
    return db_modele


def get_modele_annees(
    *, session: Session, modele_id: uuid.UUID
) -> tuple[list[ModeleAnnee], int]:
    statement = (
        select(ModeleAnnee)
        .where(ModeleAnnee.modele_id == modele_id)
        .order_by(col(ModeleAnnee.annee).desc())
    )
    annees = session.exec(statement).all()
    count_statement = select(func.count()).select_from(ModeleAnnee).where(
        ModeleAnnee.modele_id == modele_id
    )
    count = session.exec(count_statement).one()
    return list(annees), count


def get_modele_annee_by_annee(
    *, session: Session, modele_id: uuid.UUID, annee: int
) -> ModeleAnnee | None:
    statement = select(ModeleAnnee).where(
        ModeleAnnee.modele_id == modele_id, ModeleAnnee.annee == annee
    )
    return session.exec(statement).first()


def create_modele_annee(
    *, session: Session, annee_in: ModeleAnneeCreate
) -> ModeleAnnee:
    annee = ModeleAnnee.model_validate(annee_in)
    session.add(annee)
    session.commit()
    session.refresh(annee)
    return annee


def update_modele_annee(
    *, session: Session, db_annee: ModeleAnnee, annee_in: ModeleAnneeUpdate
) -> ModeleAnnee:
    annee_data = annee_in.model_dump(exclude_unset=True)
    db_annee.sqlmodel_update(annee_data)
    session.add(db_annee)
    session.commit()
    session.refresh(db_annee)
    return db_annee


def get_vendeurs(*, session: Session) -> tuple[list[Vendeur], int]:
    statement = select(Vendeur).order_by(col(Vendeur.nom))
    vendeurs = session.exec(statement).all()
    count = session.exec(select(func.count()).select_from(Vendeur)).one()
    return list(vendeurs), count


def get_vendeur_by_nom(*, session: Session, nom: str) -> Vendeur | None:
    statement = select(Vendeur).where(func.lower(Vendeur.nom) == nom.lower())
    return session.exec(statement).first()


def create_vendeur(*, session: Session, vendeur_in: VendeurCreate) -> Vendeur:
    vendeur = Vendeur.model_validate(vendeur_in)
    session.add(vendeur)
    session.commit()
    session.refresh(vendeur)
    return vendeur


def update_vendeur(
    *, session: Session, db_vendeur: Vendeur, vendeur_in: VendeurUpdate
) -> Vendeur:
    vendeur_data = vendeur_in.model_dump(exclude_unset=True)
    db_vendeur.sqlmodel_update(vendeur_data)
    session.add(db_vendeur)
    session.commit()
    session.refresh(db_vendeur)
    return db_vendeur


def get_or_create_parametres_financiers(*, session: Session) -> ParametresFinanciers:
    parametres = session.exec(select(ParametresFinanciers)).first()
    if not parametres:
        parametres = ParametresFinanciers()
        session.add(parametres)
        session.commit()
        session.refresh(parametres)
    return parametres


def update_parametres_financiers(
    *,
    session: Session,
    db_parametres: ParametresFinanciers,
    parametres_in: ParametresFinanciersUpdate,
) -> ParametresFinanciers:
    parametres_data = parametres_in.model_dump(exclude_unset=True)
    db_parametres.sqlmodel_update(parametres_data, update={"updated_at": get_datetime_utc()})
    session.add(db_parametres)
    session.commit()
    session.refresh(db_parametres)
    return db_parametres


# ---------------------------------------------------------------------------
# Messagerie temps réel par dossier
# ---------------------------------------------------------------------------


def create_message(
    *,
    session: Session,
    demande_id: uuid.UUID,
    sender: User,
    is_admin_sender: bool,
    message_in: ChatMessageCreate,
) -> ChatMessage:
    message = ChatMessage(
        demande_id=demande_id,
        sender_id=sender.id,
        sender_role="admin" if is_admin_sender else "client",
        contenu=message_in.contenu,
        lu_par_admin=is_admin_sender,
        lu_par_client=not is_admin_sender,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def get_messages(*, session: Session, demande_id: uuid.UUID) -> tuple[list[ChatMessage], int]:
    statement = (
        select(ChatMessage)
        .where(ChatMessage.demande_id == demande_id)
        .order_by(col(ChatMessage.created_at))
    )
    messages = session.exec(statement).all()
    count = session.exec(
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.demande_id == demande_id)
    ).one()
    return list(messages), count


def mark_messages_read(
    *, session: Session, demande_id: uuid.UUID, is_admin_viewer: bool
) -> None:
    field = ChatMessage.lu_par_admin if is_admin_viewer else ChatMessage.lu_par_client
    statement = select(ChatMessage).where(
        ChatMessage.demande_id == demande_id, field == False  # noqa: E712
    )
    for message in session.exec(statement).all():
        if is_admin_viewer:
            message.lu_par_admin = True
        else:
            message.lu_par_client = True
        session.add(message)
    session.commit()


def count_unread_messages(
    *, session: Session, demande_id: uuid.UUID, is_admin_viewer: bool
) -> int:
    field = ChatMessage.lu_par_admin if is_admin_viewer else ChatMessage.lu_par_client
    statement = (
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.demande_id == demande_id, field == False)  # noqa: E712
    )
    return session.exec(statement).one()


# ---------------------------------------------------------------------------
# Messagerie temps réel générique (admin <-> investisseur/admin) + boîte de
# réception unifiée "Messagerie" (tous les utilisateurs, quel que soit leur
# canal réel — dossier de crédit pour un client, canal générique sinon)
# ---------------------------------------------------------------------------


def create_user_message(
    *,
    session: Session,
    user_id: uuid.UUID,
    sender: User,
    is_admin_sender: bool,
    message_in: UserMessageCreate,
) -> UserMessage:
    message = UserMessage(
        user_id=user_id,
        sender_id=sender.id,
        sender_role="admin" if is_admin_sender else "user",
        contenu=message_in.contenu,
        lu_par_admin=is_admin_sender,
        lu_par_user=not is_admin_sender,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def get_user_messages(
    *, session: Session, user_id: uuid.UUID
) -> tuple[list[UserMessage], int]:
    statement = (
        select(UserMessage)
        .where(UserMessage.user_id == user_id)
        .order_by(col(UserMessage.created_at))
    )
    messages = session.exec(statement).all()
    count = session.exec(
        select(func.count()).select_from(UserMessage).where(UserMessage.user_id == user_id)
    ).one()
    return list(messages), count


def mark_user_messages_read(
    *, session: Session, user_id: uuid.UUID, is_admin_viewer: bool
) -> None:
    field = UserMessage.lu_par_admin if is_admin_viewer else UserMessage.lu_par_user
    statement = select(UserMessage).where(
        UserMessage.user_id == user_id, field == False  # noqa: E712
    )
    for message in session.exec(statement).all():
        if is_admin_viewer:
            message.lu_par_admin = True
        else:
            message.lu_par_user = True
        session.add(message)
    session.commit()


def count_unread_user_messages(
    *, session: Session, user_id: uuid.UUID, is_admin_viewer: bool
) -> int:
    field = UserMessage.lu_par_admin if is_admin_viewer else UserMessage.lu_par_user
    statement = (
        select(func.count())
        .select_from(UserMessage)
        .where(UserMessage.user_id == user_id, field == False)  # noqa: E712
    )
    return session.exec(statement).one()


def get_messagerie_conversations(
    *, session: Session, exclude_user_id: uuid.UUID | None = None
) -> list[MessagerieConversationPublic]:
    users = session.exec(select(User)).all()
    conversations = []
    for u in users:
        if exclude_user_id is not None and u.id == exclude_user_id:
            continue

        if u.is_admin or u.is_superuser or u.is_investisseur:
            last = session.exec(
                select(UserMessage)
                .where(UserMessage.user_id == u.id)
                .order_by(col(UserMessage.created_at).desc())
                .limit(1)
            ).first()
            unread_count = count_unread_user_messages(
                session=session, user_id=u.id, is_admin_viewer=True
            )
            conversations.append(
                MessagerieConversationPublic(
                    user_id=u.id,
                    user_name=u.full_name or u.email,
                    user_email=u.email,
                    is_admin=u.is_admin,
                    is_investisseur=u.is_investisseur,
                    is_superuser=u.is_superuser,
                    conversation_kind="user",
                    conversation_id=u.id,
                    last_message=last.contenu if last else None,
                    last_message_at=last.created_at if last else None,
                    unread_count=unread_count,
                )
            )
        else:
            demande = session.exec(
                select(Demande)
                .where(Demande.owner_id == u.id)
                .order_by(col(Demande.created_at).desc())
                .limit(1)
            ).first()
            last_message = None
            last_message_at = None
            unread_count = 0
            if demande:
                last = session.exec(
                    select(ChatMessage)
                    .where(ChatMessage.demande_id == demande.id)
                    .order_by(col(ChatMessage.created_at).desc())
                    .limit(1)
                ).first()
                last_message = last.contenu if last else None
                last_message_at = last.created_at if last else None
                unread_count = count_unread_messages(
                    session=session, demande_id=demande.id, is_admin_viewer=True
                )
            conversations.append(
                MessagerieConversationPublic(
                    user_id=u.id,
                    user_name=u.full_name or u.email,
                    user_email=u.email,
                    is_admin=False,
                    is_investisseur=False,
                    is_superuser=False,
                    conversation_kind="demande",
                    conversation_id=demande.id if demande else None,
                    last_message=last_message,
                    last_message_at=last_message_at,
                    unread_count=unread_count,
                )
            )

    conversations.sort(
        key=lambda c: c.last_message_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return conversations


# ---------------------------------------------------------------------------
# Dashboard investisseur : capital investi + distributions saisis par un
# admin, encours/contrats/NPL/taux de remboursement/répartition calculés en
# direct depuis l'échéancier réel — même logique que le module Recouvrement.
# ---------------------------------------------------------------------------


def list_investisseurs(*, session: Session) -> list[User]:
    statement = select(User).where(User.is_investisseur == True)  # noqa: E712
    return list(session.exec(statement).all())


def get_investisseur_profil(
    *, session: Session, investisseur_id: uuid.UUID
) -> InvestisseurProfil | None:
    statement = select(InvestisseurProfil).where(
        InvestisseurProfil.investisseur_id == investisseur_id
    )
    return session.exec(statement).first()


def upsert_investisseur_profil(
    *, session: Session, investisseur_id: uuid.UUID, profil_in: InvestisseurProfilUpdate
) -> InvestisseurProfil:
    profil = get_investisseur_profil(session=session, investisseur_id=investisseur_id)
    if not profil:
        profil = InvestisseurProfil(investisseur_id=investisseur_id)
    for key, value in profil_in.model_dump(exclude_unset=True).items():
        setattr(profil, key, value)
    session.add(profil)
    session.commit()
    session.refresh(profil)
    return profil


def create_distribution(
    *, session: Session, investisseur_id: uuid.UUID, distribution_in: DistributionCreate
) -> Distribution:
    distribution = Distribution.model_validate(
        distribution_in, update={"investisseur_id": investisseur_id}
    )
    session.add(distribution)
    session.commit()
    session.refresh(distribution)
    return distribution


def get_distributions(*, session: Session, investisseur_id: uuid.UUID) -> list[Distribution]:
    statement = (
        select(Distribution)
        .where(Distribution.investisseur_id == investisseur_id)
        .order_by(col(Distribution.date_distribution).desc())
    )
    return list(session.exec(statement).all())


def get_distribution(*, session: Session, distribution_id: uuid.UUID) -> Distribution | None:
    return session.get(Distribution, distribution_id)


def update_distribution(
    *, session: Session, distribution: Distribution, distribution_in: DistributionUpdate
) -> Distribution:
    for key, value in distribution_in.model_dump(exclude_unset=True).items():
        setattr(distribution, key, value)
    session.add(distribution)
    session.commit()
    session.refresh(distribution)
    return distribution


def delete_distribution(*, session: Session, distribution: Distribution) -> None:
    session.delete(distribution)
    session.commit()


def _prochain_rapport_officiel() -> date:
    today = date.today()
    for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
        candidate = date(today.year, month, day)
        if candidate >= today:
            return candidate
    return date(today.year + 1, 3, 31)


def get_fonds_performance(*, session: Session) -> dict:
    demandes = list_demandes_avec_echeancier(session=session)
    today = date.today()
    contrats_actifs = 0
    encours_total = 0
    en_retard_90 = 0
    total_echeances_dues = 0
    total_echeances_a_temps = 0

    for demande in demandes:
        echeances = get_echeances(session=session, demande_id=demande.id)
        actions = get_actions_recouvrement(session=session, demande_id=demande.id)
        info = compute_recouvrement(echeances, actions)

        impayees = [e for e in echeances if not e.payee]
        if impayees:
            contrats_actifs += 1
            encours_total += sum(e.montant for e in impayees)
        if info["jours_retard"] >= 90:
            en_retard_90 += 1

        for e in echeances:
            if e.date_echeance <= today:
                total_echeances_dues += 1
                if e.payee and e.payee_le and e.payee_le.date() <= e.date_echeance:
                    total_echeances_a_temps += 1

    npl_90j_pct = round(en_retard_90 / contrats_actifs * 100, 1) if contrats_actifs else 0.0
    taux_remboursement_pct = (
        round(total_echeances_a_temps / total_echeances_dues * 100, 1)
        if total_echeances_dues
        else 0.0
    )
    return {
        "encours_total": encours_total,
        "contrats_actifs": contrats_actifs,
        "npl_90j_pct": npl_90j_pct,
        "taux_remboursement_pct": taux_remboursement_pct,
        "lgd_note": "Aucun défaut à ce stade" if en_retard_90 == 0 else "En cours d'évaluation",
        "ratio_charges_ca": None,
        "prochain_rapport_officiel": _prochain_rapport_officiel(),
    }


def get_repartition_marques(*, session: Session) -> list[dict]:
    demandes = list_demandes_avec_echeancier(session=session)
    counts: dict[str, int] = {}
    for demande in demandes:
        label = demande.marque or "Autres"
        counts[label] = counts.get(label, 0) + 1
    return [
        {"marque": marque, "count": count}
        for marque, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]


def get_investisseur_dashboard(*, session: Session, investisseur_id: uuid.UUID) -> dict:
    profil = get_investisseur_profil(session=session, investisseur_id=investisseur_id)
    montant_investi = profil.montant_investi if profil else 0
    date_investissement = profil.date_investissement if profil else None

    distributions = get_distributions(session=session, investisseur_id=investisseur_id)
    dividendes_recus = sum(
        d.montant for d in distributions if d.statut == StatutDistribution.verse
    )

    current_year = date.today().year
    dividendes_ytd = sum(
        d.montant
        for d in distributions
        if d.statut == StatutDistribution.verse and d.date_distribution.year == current_year
    )
    rendement_ytd_pct = (
        round(dividendes_ytd / montant_investi * 100, 1) if montant_investi else None
    )

    tri_calcule_pct = None
    if montant_investi and date_investissement:
        years_elapsed = max((date.today() - date_investissement).days / 365.25, 0.5)
        tri_calcule_pct = round(dividendes_recus / montant_investi / years_elapsed * 100, 1)

    prochain_versement = next(
        (
            d
            for d in sorted(distributions, key=lambda d: d.date_distribution)
            if d.statut == StatutDistribution.prevu
        ),
        None,
    )

    return {
        "investisseur_id": investisseur_id,
        "montant_investi": montant_investi,
        "date_investissement": date_investissement,
        "dividendes_recus": dividendes_recus,
        "rendement_ytd_pct": rendement_ytd_pct,
        "tri_calcule_pct": tri_calcule_pct,
        "prochain_versement": prochain_versement,
        "distributions": distributions,
        "repartition_marques": get_repartition_marques(session=session),
        "fonds": get_fonds_performance(session=session),
    }
