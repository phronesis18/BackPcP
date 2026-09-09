import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session

from app.api.deps import CurrentUser, SessionDep
from app.crud import (
    count_unread_messages,
    create_contrat,
    create_demande,
    create_demande_document,
    get_contrat,
    get_demande,
    get_demandes,
)
from app.models import (
    ContratCreate,
    ContratPublic,
    Demande,
    DemandeCreate,
    DemandePublic,
    DemandeUpdate,
    DemandesPublic,
    Document,
    DocumentCreate,
    DocumentPublic,
    Message,
    StatutDemande,
    StatutDocument,
    User,
)
from app.scoring import compute_score

router = APIRouter(prefix="/demandes", tags=["demandes"])


def to_demande_public(session: Session, demande: Demande, viewer: User) -> DemandePublic:
    public = DemandePublic.model_validate(demande)
    public.score = compute_score(demande)
    if demande.owner:
        public.owner_phone = demande.owner.phone
        public.owner_email = demande.owner.email
    is_admin_viewer = viewer.is_superuser or viewer.is_admin
    public.unread_count = count_unread_messages(
        session=session, demande_id=demande.id, is_admin_viewer=is_admin_viewer
    )
    return public


@router.get("/", response_model=DemandesPublic)
def read_demandes(
    session: SessionDep,
    current_user: CurrentUser,
    statut: StatutDemande | None = None,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve credit applications.

    Regular users see only their own applications, superusers see everything.
    Brouillons (drafts) are excluded unless `statut=brouillon` is explicitly requested.
    """
    is_back_office = current_user.is_superuser or current_user.is_admin
    owner_id = None if is_back_office else current_user.id
    demandes, count = get_demandes(
        session=session, owner_id=owner_id, statut=statut, skip=skip, limit=limit
    )
    return DemandesPublic(
        data=[to_demande_public(session, d, current_user) for d in demandes], count=count
    )


@router.get("/{demande_id}", response_model=DemandePublic)
def read_demande(
    session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID
) -> Any:
    """
    Get a specific credit application by id.
    """
    demande = get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if (
        not (current_user.is_superuser or current_user.is_admin)
        and demande.owner_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    return to_demande_public(session, demande, current_user)


@router.post("/", response_model=DemandePublic, status_code=201)
def create_demande_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_in: DemandeCreate,
) -> Any:
    """
    Create a new credit application for the authenticated user.
    """
    demande = create_demande(
        session=session, demande_in=demande_in, owner_id=current_user.id
    )
    return to_demande_public(session, demande, current_user)


@router.post("/{demande_id}/documents", response_model=DocumentPublic, status_code=201)
def create_document_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    doc_in: DocumentCreate,
) -> Any:
    """
    Add a document (metadata) to an existing credit application.
    """
    demande = get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if (
        not (current_user.is_superuser or current_user.is_admin)
        and demande.owner_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    return create_demande_document(session=session, demande_id=demande_id, doc_in=doc_in)


@router.post("/{demande_id}/documents/{document_id}/upload")
async def upload_document(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    document_id: uuid.UUID,
    file: UploadFile = File(...),
) -> Any:
    """
    Upload the file for a specific document of a demande.
    """
    demande = get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if (
        not (current_user.is_superuser or current_user.is_admin)
        and demande.owner_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    document = session.get(Document, document_id)
    if not document or document.demande_id != demande_id:
        raise HTTPException(status_code=404, detail="Document introuvable")

    document.fichier = await file.read()
    document.content_type = file.content_type
    document.nom = file.filename
    document.statut = StatutDocument.uploaded
    session.add(document)
    session.commit()
    session.refresh(document)
    return to_demande_public(session, demande, current_user)


@router.get("/{demande_id}/documents/{document_id}/download")
def download_document(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Response:
    """
    Download the file of a specific document of a demande.
    """
    demande = get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if (
        not (current_user.is_superuser or current_user.is_admin)
        and demande.owner_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    document = session.get(Document, document_id)
    if not document or document.demande_id != demande_id or not document.fichier:
        raise HTTPException(status_code=404, detail="Document introuvable")

    return Response(
        content=document.fichier,
        media_type=document.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{document.nom}"'},
    )


@router.patch("/{demande_id}", response_model=DemandePublic)
def update_demande(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    demande_in: DemandeUpdate,
) -> Any:
    """
    Update a credit application (e.g. change its status).
    """
    demande = get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if (
        not (current_user.is_superuser or current_user.is_admin)
        and demande.owner_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    update_dict = demande_in.model_dump(exclude_unset=True)
    demande.sqlmodel_update(update_dict)
    session.add(demande)
    session.commit()
    session.refresh(demande)
    return to_demande_public(session, demande, current_user)


@router.delete("/{demande_id}")
def delete_demande(
    session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID
) -> Message:
    """
    Delete a credit application.
    """
    demande = get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if (
        not (current_user.is_superuser or current_user.is_admin)
        and demande.owner_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    session.delete(demande)
    session.commit()
    return Message(message="Demande supprimée avec succès")


@router.get("/{demande_id}/contrat", response_model=ContratPublic)
def read_contrat(
    session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID
) -> Any:
    """
    Get the signed contract for a credit application, if it exists.
    """
    demande = get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if (
        not (current_user.is_superuser or current_user.is_admin)
        and demande.owner_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    contrat = get_contrat(session=session, demande_id=demande_id)
    if not contrat:
        raise HTTPException(status_code=404, detail="Contrat introuvable")
    return contrat


@router.post("/{demande_id}/contrat", response_model=ContratPublic, status_code=201)
def create_contrat_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    contrat_in: ContratCreate,
) -> Any:
    """
    Save the signed contract for a credit application. Only the client who
    owns the demande (or an admin, for support purposes) can sign it. A
    demande can only have one contract — once signed, it cannot be replaced
    through this route.
    """
    demande = get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    if not (
        current_user.is_superuser
        or current_user.is_admin
        or demande.owner_id == current_user.id
    ):
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    if get_contrat(session=session, demande_id=demande_id):
        raise HTTPException(status_code=409, detail="Ce dossier a déjà un contrat signé")
    return create_contrat(session=session, demande_id=demande_id, contrat_in=contrat_in)
