import enum
import uuid
from datetime import date, datetime, timezone

from pydantic import EmailStr
from sqlalchemy import Date, DateTime, LargeBinary
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


class SituationMatrimoniale(str, enum.Enum):
    celibataire = "celibataire"
    marie = "marie"
    divorce = "divorce"
    veuf = "veuf"


class StatutDemande(str, enum.Enum):
    brouillon = "brouillon"
    soumise = "soumise"
    en_etude = "en_etude"
    validee = "validee"
    rejectee = "rejetee"
    signee = "signee"


class StatutDocument(str, enum.Enum):
    pending = "pending"
    uploaded = "uploaded"
    processing = "processing"
    valide = "valide"


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    phone: str | None = Field(default=None, unique=True, index=True, max_length=20)
    is_active: bool = True
    is_superuser: bool = False
    is_admin: bool = False
    is_investisseur: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=8, max_length=20)
    email: EmailStr | None = Field(default=None, max_length=255)
    password: str = Field(min_length=8, max_length=128)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    demandes: list["Demande"] = Relationship(
        back_populates="owner", cascade_delete=True
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# ---------------------------------------------------------------------------
# Credit application ("Demande") domain models
# ---------------------------------------------------------------------------


class Document(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    type: str = Field(max_length=120)
    nom: str | None = Field(default=None, max_length=255)
    statut: StatutDocument = Field(default=StatutDocument.pending)
    ocr: bool = False
    content_type: str | None = Field(default=None, max_length=100)
    fichier: bytes | None = Field(default=None, sa_type=LargeBinary)
    demande_id: uuid.UUID = Field(
        foreign_key="demande.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    demande: "Demande" = Relationship(back_populates="documents")


class Demande(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # --- Identité du demandeur ---
    prenom: str = Field(max_length=100)
    nom: str = Field(max_length=100)
    date_naissance: date | None = Field(default=None, sa_type=Date)  # type: ignore
    lieu_naissance: str | None = Field(default=None, max_length=100)
    cni_number: str | None = Field(default=None, max_length=50)
    situation_matrimoniale: SituationMatrimoniale | None = Field(default=None)
    profession: str | None = Field(default=None, max_length=120)
    employeur: str | None = Field(default=None, max_length=120)
    revenu_mensuel: int | None = Field(default=None)
    anciennete_annees: int | None = Field(default=None)
    adresse: str | None = Field(default=None, max_length=255)

    # --- Véhicule & plan de financement ---
    marque: str | None = Field(default=None, max_length=50)
    modele: str | None = Field(default=None, max_length=50)
    annee: int | None = Field(default=None)
    kilometrage: int | None = Field(default=None)
    vendeur: str | None = Field(default=None, max_length=120)
    prix_vehicule: int = Field(default=0)
    duree_mois: int = Field(default=48)
    mensualite: int | None = Field(default=None)
    taux_teg: float | None = Field(default=22.0)

    # --- Suivi ---
    statut: StatutDemande = Field(default=StatutDemande.soumise)

    # --- Relations ---
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner: User | None = Relationship(back_populates="demandes")
    documents: list[Document] = Relationship(
        back_populates="demande", cascade_delete=True
    )


# ---------------------------------------------------------------------------
# Catalogue véhicules (Marque -> Modele -> ModeleAnnee)
# ---------------------------------------------------------------------------


class MarqueBase(SQLModel):
    nom: str = Field(max_length=80, unique=True, index=True)


class MarqueCreate(MarqueBase):
    pass


class MarqueUpdate(SQLModel):
    nom: str | None = Field(default=None, max_length=80)


class Marque(MarqueBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    modeles: list["Modele"] = Relationship(
        back_populates="marque", cascade_delete=True
    )


class MarquePublic(MarqueBase):
    id: uuid.UUID
    created_at: datetime | None = None


class MarquesPublic(SQLModel):
    data: list[MarquePublic]
    count: int


class ModeleBase(SQLModel):
    nom: str = Field(max_length=80)


class ModeleCreate(ModeleBase):
    marque_id: uuid.UUID


class ModeleUpdate(SQLModel):
    nom: str | None = Field(default=None, max_length=80)


class Modele(ModeleBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    marque_id: uuid.UUID = Field(
        foreign_key="marque.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    marque: Marque | None = Relationship(back_populates="modeles")
    annees: list["ModeleAnnee"] = Relationship(
        back_populates="modele", cascade_delete=True
    )


class ModelePublic(ModeleBase):
    id: uuid.UUID
    marque_id: uuid.UUID
    created_at: datetime | None = None


class ModelesPublic(SQLModel):
    data: list[ModelePublic]
    count: int


class ModeleAnneeBase(SQLModel):
    annee: int
    kilometrage_min: int | None = None
    kilometrage_max: int | None = None


class ModeleAnneeCreate(ModeleAnneeBase):
    modele_id: uuid.UUID


class ModeleAnneeUpdate(SQLModel):
    annee: int | None = None
    kilometrage_min: int | None = None
    kilometrage_max: int | None = None


class ModeleAnnee(ModeleAnneeBase, table=True):
    __tablename__ = "modele_annee"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    modele_id: uuid.UUID = Field(
        foreign_key="modele.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    modele: Modele | None = Relationship(back_populates="annees")


class ModeleAnneePublic(ModeleAnneeBase):
    id: uuid.UUID
    modele_id: uuid.UUID
    created_at: datetime | None = None


class ModeleAnneesPublic(SQLModel):
    data: list[ModeleAnneePublic]
    count: int


# ---------------------------------------------------------------------------
# Schemas (Pydantic) for Demande / Document
# ---------------------------------------------------------------------------


class DocumentBase(SQLModel):
    type: str = Field(max_length=120)
    nom: str | None = Field(default=None, max_length=255)
    statut: StatutDocument = Field(default=StatutDocument.pending)
    ocr: bool = False


class DocumentCreate(DocumentBase):
    pass


class DocumentPublic(DocumentBase):
    id: uuid.UUID
    demande_id: uuid.UUID
    created_at: datetime | None = None


class DocumentsPublic(SQLModel):
    data: list[DocumentPublic]
    count: int


class DemandeBase(SQLModel):
    prenom: str = Field(max_length=100)
    nom: str = Field(max_length=100)
    date_naissance: date | None = None
    lieu_naissance: str | None = Field(default=None, max_length=100)
    cni_number: str | None = Field(default=None, max_length=50)
    situation_matrimoniale: SituationMatrimoniale | None = None
    profession: str | None = Field(default=None, max_length=120)
    employeur: str | None = Field(default=None, max_length=120)
    revenu_mensuel: int | None = None
    anciennete_annees: int | None = None
    adresse: str | None = Field(default=None, max_length=255)
    marque: str | None = Field(default=None, max_length=50)
    modele: str | None = Field(default=None, max_length=50)
    annee: int | None = None
    kilometrage: int | None = None
    vendeur: str | None = Field(default=None, max_length=120)
    prix_vehicule: int = Field(default=0)
    duree_mois: int = Field(default=48)
    mensualite: int | None = None
    taux_teg: float | None = Field(default=22.0)
    statut: StatutDemande = Field(default=StatutDemande.soumise)


class DemandeCreate(DemandeBase):
    documents: list[DocumentCreate] | None = Field(default_factory=list)


class DemandeUpdate(SQLModel):
    prenom: str | None = Field(default=None, max_length=100)
    nom: str | None = Field(default=None, max_length=100)
    date_naissance: date | None = None
    lieu_naissance: str | None = Field(default=None, max_length=100)
    cni_number: str | None = Field(default=None, max_length=50)
    situation_matrimoniale: SituationMatrimoniale | None = None
    profession: str | None = Field(default=None, max_length=120)
    employeur: str | None = Field(default=None, max_length=120)
    revenu_mensuel: int | None = None
    anciennete_annees: int | None = None
    adresse: str | None = Field(default=None, max_length=255)
    marque: str | None = Field(default=None, max_length=50)
    modele: str | None = Field(default=None, max_length=50)
    annee: int | None = None
    kilometrage: int | None = None
    vendeur: str | None = Field(default=None, max_length=120)
    prix_vehicule: int | None = None
    duree_mois: int | None = None
    mensualite: int | None = None
    taux_teg: float | None = None
    statut: StatutDemande | None = None


class DemandePublic(DemandeBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None
    documents: list[DocumentPublic] = Field(default_factory=list)


class DemandesPublic(SQLModel):
    data: list[DemandePublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
