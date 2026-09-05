import uuid
from typing import Any

from sqlmodel import Session, col, func, select

from app.core.security import get_password_hash, verify_password
from app.models import (
    Demande,
    DemandeCreate,
    Document,
    Marque,
    MarqueCreate,
    MarqueUpdate,
    Modele,
    ModeleAnnee,
    ModeleAnneeCreate,
    ModeleAnneeUpdate,
    ModeleCreate,
    ModeleUpdate,
    User,
    UserCreate,
    UserUpdate,
)


def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
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
    *, session: Session, owner_id: uuid.UUID | None = None, skip: int = 0, limit: int = 100
) -> tuple[list[Demande], int]:
    statement = select(Demande)
    count_statement = select(func.count()).select_from(Demande)
    if owner_id is not None:
        statement = statement.where(Demande.owner_id == owner_id)
        count_statement = count_statement.where(Demande.owner_id == owner_id)

    count = session.exec(count_statement).one()
    demandes = (
        session.exec(
            statement.order_by(col(Demande.created_at).desc())
            .offset(skip)
            .limit(limit)
        ).all()
    )
    return list(demandes), count


def get_demande(*, session: Session, demande_id: uuid.UUID) -> Demande | None:
    return session.get(Demande, demande_id)


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
