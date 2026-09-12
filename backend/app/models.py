import enum
import uuid
from datetime import date, datetime, timezone

from pydantic import EmailStr
from sqlalchemy import JSON, Date, DateTime, LargeBinary, Text
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
    complement_demande = "complement_demande"
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
    # True for accounts an admin creates on someone's behalf (they log in with
    # the temporary password emailed to them and must pick their own before
    # doing anything else) — always False for self-registration.
    must_change_password: bool = Field(default=False)
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
    must_change_password: bool = False


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
    # Résultat de la dernière extraction OCR (Claude Vision) : champs lus et
    # écarts éventuels avec le déclaratif. None tant qu'aucune analyse n'a
    # été lancée — voir app/ocr.py pour le format exact.
    ocr_resultat: dict | None = Field(default=None, sa_type=JSON)
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

    @property
    def has_file(self) -> bool:
        return self.fichier is not None


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


class VendeurBase(SQLModel):
    nom: str = Field(max_length=120, unique=True, index=True)


class VendeurCreate(VendeurBase):
    pass


class VendeurUpdate(SQLModel):
    nom: str | None = Field(default=None, max_length=120)


class Vendeur(VendeurBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class VendeurPublic(VendeurBase):
    id: uuid.UUID
    created_at: datetime | None = None


class VendeursPublic(SQLModel):
    data: list[VendeurPublic]
    count: int


# ---------------------------------------------------------------------------
# Paramètres financiers (TEG, apport) — ligne unique modifiable par l'admin
# ---------------------------------------------------------------------------


class ParametresFinanciersBase(SQLModel):
    taux_teg_annuel: float = Field(default=22.0)
    taux_apport: float = Field(default=0.25)
    # Pourcentage (0-100) du score disponible à partir duquel un dossier est
    # approuvé automatiquement. Un pourcentage plutôt qu'un score absolu : le
    # max réellement atteignable évolue (400/850 aujourd'hui tant que Mobile
    # Money/BCEAO ne sont pas connectés), donc ce seuil doit parler la même
    # langue que ce qui est affiché, quel que soit le max du moment. Voir
    # app/scoring.py.
    seuil_scoring_auto: int = Field(default=75)
    montant_min: int = Field(default=1_000_000)
    montant_max: int = Field(default=30_000_000)


class ParametresFinanciersUpdate(SQLModel):
    taux_teg_annuel: float | None = None
    taux_apport: float | None = None
    seuil_scoring_auto: int | None = None
    montant_min: int | None = None
    montant_max: int | None = None


class ParametresFinanciers(ParametresFinanciersBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ParametresFinanciersPublic(ParametresFinanciersBase):
    id: uuid.UUID
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# Schemas (Pydantic) for Demande / Document / Contrat
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
    has_file: bool = False
    ocr_resultat: dict | None = None


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


class ScoreAxis(SQLModel):
    key: str
    label: str
    valeur: int | None
    max: int
    disponible: bool


class ScoreSignal(SQLModel):
    type: str  # "ok" | "warning" | "unavailable"
    label: str


class ScoreSource(SQLModel):
    label: str
    disponible: bool


class ScorePublic(SQLModel):
    total: int = 0
    max: int = 0
    decision: str = "indetermine"
    axes: list[ScoreAxis] = Field(default_factory=list)
    signaux: list[ScoreSignal] = Field(default_factory=list)
    sources: list[ScoreSource] = Field(default_factory=list)


class DemandePublic(DemandeBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    owner_phone: str | None = None
    owner_email: str | None = None
    created_at: datetime | None = None
    documents: list[DocumentPublic] = Field(default_factory=list)
    score: ScorePublic = Field(default_factory=ScorePublic)
    unread_count: int = 0


class DemandesPublic(SQLModel):
    data: list[DemandePublic]
    count: int


class Contrat(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    demande_id: uuid.UUID = Field(
        foreign_key="demande.id", nullable=False, unique=True, ondelete="CASCADE"
    )
    contenu: str = Field(sa_type=Text)  # type: ignore
    signature: str = Field(sa_type=Text)  # type: ignore
    signed_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ContratCreate(SQLModel):
    contenu: str
    signature: str


class ContratPublic(SQLModel):
    id: uuid.UUID
    demande_id: uuid.UUID
    contenu: str
    signature: str
    signed_at: datetime


# ---------------------------------------------------------------------------
# Recouvrement — échéancier réel (généré à la signature du contrat) et
# journal des actions de relance. Il n'existe aucun connecteur SMS/WhatsApp/
# GPS-immobilisateur réel à ce jour : les actions ci-dessous sont des
# constats manuels consignés par un admin, pas des envois automatiques.
# ---------------------------------------------------------------------------


class Echeance(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    demande_id: uuid.UUID = Field(
        foreign_key="demande.id", nullable=False, ondelete="CASCADE"
    )
    numero: int
    date_echeance: date = Field(sa_type=Date)  # type: ignore
    montant: int
    payee: bool = Field(default=False)
    payee_le: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)  # type: ignore
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class EcheancePublic(SQLModel):
    id: uuid.UUID
    demande_id: uuid.UUID
    numero: int
    date_echeance: date
    montant: int
    payee: bool
    payee_le: datetime | None


class EcheancesPublic(SQLModel):
    data: list[EcheancePublic]
    count: int


# Types d'action reconnus par la route — tout autre type est rejeté (422).
TYPES_ACTION_RECOUVREMENT = {
    "sms",
    "whatsapp",
    "appel",
    "mise_en_demeure",
    "coupe_moteur",
    "reactivation",
    "contentieux",
}


class ActionRecouvrementBase(SQLModel):
    type: str = Field(max_length=30)
    note: str | None = Field(default=None, max_length=500)


class ActionRecouvrementCreate(ActionRecouvrementBase):
    pass


class ActionRecouvrement(ActionRecouvrementBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    demande_id: uuid.UUID = Field(
        foreign_key="demande.id", nullable=False, ondelete="CASCADE"
    )
    created_by_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ActionRecouvrementPublic(ActionRecouvrementBase):
    id: uuid.UUID
    demande_id: uuid.UUID
    created_by_nom: str
    created_at: datetime | None = None


class ActionsRecouvrementPublic(SQLModel):
    data: list[ActionRecouvrementPublic]
    count: int


class RecouvrementInfo(SQLModel):
    en_retard: bool = False
    jours_retard: int = 0
    montant_du: int = 0
    # "j1_15" | "j16_30" | "coupe_moteur" | None (pas de retard)
    phase: str | None = None
    moteur_coupe: bool = False
    derniere_action: ActionRecouvrementPublic | None = None
    prochaine_action_suggeree: str | None = None
    prochaine_action_date: date | None = None


class DossierRecouvrementPublic(SQLModel):
    demande_id: uuid.UUID
    client_nom: str
    # Le frontend compose la référence lisible (PCP-<année>-<id>) à partir de
    # created_at, comme partout ailleurs — pas de logique de formatage dupliquée ici.
    created_at: datetime | None = None
    recouvrement: RecouvrementInfo


class DossiersRecouvrementPublic(SQLModel):
    data: list[DossierRecouvrementPublic]
    resume: dict[str, int]


# ---------------------------------------------------------------------------
# Fleet Monitor — fiche véhicule réelle, une par contrat signé. Il n'existe
# aucun boîtier GPS/immobilisateur connecté à ce jour : la plaque et la
# position sont saisies à la main par un admin, et le statut moteur reflète
# le journal ActionRecouvrement — la même source que le module Recouvrement,
# pour ne jamais avoir deux écrans qui se contredisent sur "moteur coupé".
# ---------------------------------------------------------------------------


class VehiculeFlotteBase(SQLModel):
    plaque: str | None = Field(default=None, max_length=20)
    position_label: str | None = Field(default=None, max_length=120)


class VehiculeFlotteUpdate(SQLModel):
    plaque: str | None = Field(default=None, max_length=20)
    position_label: str | None = Field(default=None, max_length=120)


class VehiculeFlotte(VehiculeFlotteBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    demande_id: uuid.UUID = Field(
        foreign_key="demande.id", nullable=False, unique=True, ondelete="CASCADE"
    )
    position_maj_le: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)  # type: ignore
    )
    updated_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class VehiculeFlottePublic(VehiculeFlotteBase):
    id: uuid.UUID
    demande_id: uuid.UUID
    marque: str | None = None
    modele: str | None = None
    annee: int | None = None
    conducteur_nom: str
    conducteur_telephone: str | None = None
    position_maj_le: datetime | None = None
    # "normal" | "alerte" | "coupe_moteur" — calculé, jamais stocké tel quel.
    statut: str
    moteur_coupe: bool
    jours_retard: int
    montant_du: int


class VehiculesFlottePublic(SQLModel):
    data: list[VehiculeFlottePublic]
    count: int


class FicheVehiculePublic(SQLModel):
    vehicule: VehiculeFlottePublic
    recouvrement: RecouvrementInfo
    actions: list[ActionRecouvrementPublic]


# ---------------------------------------------------------------------------
# Messagerie temps réel par dossier (admin <-> client)
# ---------------------------------------------------------------------------


class ChatMessageBase(SQLModel):
    contenu: str = Field(max_length=2000)


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessage(ChatMessageBase, table=True):
    __tablename__ = "message"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    demande_id: uuid.UUID = Field(
        foreign_key="demande.id", nullable=False, ondelete="CASCADE"
    )
    sender_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    sender_role: str = Field(max_length=10)  # snapshot "client" | "admin"
    lu_par_client: bool = Field(default=False)
    lu_par_admin: bool = Field(default=False)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ChatMessagePublic(ChatMessageBase):
    id: uuid.UUID
    demande_id: uuid.UUID
    sender_id: uuid.UUID
    sender_role: str
    sender_name: str
    created_at: datetime | None = None


class ChatMessagesPublic(SQLModel):
    data: list[ChatMessagePublic]
    count: int


# ---------------------------------------------------------------------------
# Messagerie temps réel générique (admin <-> n'importe quel utilisateur :
# investisseur, admin... les clients, eux, restent sur la messagerie par
# dossier ci-dessus, à laquelle la boîte de réception unifiée ci-dessous
# donne aussi accès).
# ---------------------------------------------------------------------------


class UserMessageBase(SQLModel):
    contenu: str = Field(max_length=2000)


class UserMessageCreate(UserMessageBase):
    pass


class UserMessage(UserMessageBase, table=True):
    __tablename__ = "user_message"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    sender_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    sender_role: str = Field(max_length=10)  # snapshot "user" | "admin"
    lu_par_user: bool = Field(default=False)
    lu_par_admin: bool = Field(default=False)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class UserMessagePublic(UserMessageBase):
    id: uuid.UUID
    user_id: uuid.UUID
    sender_id: uuid.UUID
    sender_role: str
    sender_name: str
    created_at: datetime | None = None


class UserMessagesPublic(SQLModel):
    data: list[UserMessagePublic]
    count: int


# Ligne de la boîte de réception unifiée admin ("Messagerie") : un utilisateur,
# quel que soit son rôle, avec la conversation qui lui correspond — celle liée
# à son dossier de crédit pour un client, celle du canal générique ci-dessus
# pour un investisseur ou un admin.
class MessagerieConversationPublic(SQLModel):
    user_id: uuid.UUID
    user_name: str
    user_email: str
    is_admin: bool
    is_investisseur: bool
    is_superuser: bool
    conversation_kind: str  # "demande" | "user"
    conversation_id: uuid.UUID | None = None
    last_message: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0


class MessagerieConversationsPublic(SQLModel):
    data: list[MessagerieConversationPublic]


# ---------------------------------------------------------------------------
# Dashboard investisseur — capital investi et distributions saisis par un
# admin (aucun connecteur bancaire réel), le reste (encours, contrats actifs,
# NPL, taux de remboursement, répartition par marque) est calculé en direct
# depuis l'échéancier réel des dossiers de crédit, comme le module Recouvrement.
# ---------------------------------------------------------------------------


class StatutDistribution(str, enum.Enum):
    prevu = "prevu"
    verse = "verse"


class InvestisseurProfilBase(SQLModel):
    montant_investi: int = Field(default=0)
    date_investissement: date | None = Field(default=None, sa_type=Date)  # type: ignore


class InvestisseurProfilUpdate(SQLModel):
    montant_investi: int | None = None
    date_investissement: date | None = None


class InvestisseurProfil(InvestisseurProfilBase, table=True):
    __tablename__ = "investisseur_profil"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    investisseur_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, unique=True, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class InvestisseurProfilPublic(InvestisseurProfilBase):
    investisseur_id: uuid.UUID


class DistributionBase(SQLModel):
    date_distribution: date = Field(sa_type=Date)  # type: ignore
    montant: int
    statut: StatutDistribution = Field(default=StatutDistribution.prevu)


class DistributionCreate(DistributionBase):
    pass


class DistributionUpdate(SQLModel):
    date_distribution: date | None = None
    montant: int | None = None
    statut: StatutDistribution | None = None


class Distribution(DistributionBase, table=True):
    __tablename__ = "investisseur_distribution"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    investisseur_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class DistributionPublic(DistributionBase):
    id: uuid.UUID
    investisseur_id: uuid.UUID


class DistributionsPublic(SQLModel):
    data: list[DistributionPublic]
    count: int


class RepartitionMarquePublic(SQLModel):
    marque: str
    count: int


class FondsPerformancePublic(SQLModel):
    encours_total: int
    contrats_actifs: int
    npl_90j_pct: float
    taux_remboursement_pct: float
    lgd_note: str
    ratio_charges_ca: float | None = None
    prochain_rapport_officiel: date


class InvestisseurDashboardPublic(SQLModel):
    investisseur_id: uuid.UUID
    montant_investi: int
    date_investissement: date | None = None
    dividendes_recus: int
    rendement_ytd_pct: float | None = None
    tri_calcule_pct: float | None = None
    prochain_versement: DistributionPublic | None = None
    distributions: list[DistributionPublic]
    repartition_marques: list[RepartitionMarquePublic]
    fonds: FondsPerformancePublic


class InvestisseurAdminRowPublic(SQLModel):
    investisseur_id: uuid.UUID
    nom: str
    email: str
    montant_investi: int
    date_investissement: date | None = None
    dividendes_recus: int
    prochain_versement: DistributionPublic | None = None


class InvestisseursAdminPublic(SQLModel):
    data: list[InvestisseurAdminRowPublic]


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
