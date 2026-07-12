import uuid
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep
from app.crud import create_demande, get_demande, get_demandes
from app.models import (
    Demande,
    DemandeCreate,
    DemandePublic,
    DemandeUpdate,
    DemandesPublic,
    Document,
    Message,
    StatutDocument,
)

router = APIRouter(prefix="/demandes", tags=["demandes"])


@router.get("/", response_model=DemandesPublic)
def read_demandes(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """
    Retrieve credit applications.

    Regular users see only their own applications, superusers see everything.
    """
    owner_id = None if current_user.is_superuser else current_user.id
    demandes, count = get_demandes(
        session=session, owner_id=owner_id, skip=skip, limit=limit
    )
    return DemandesPublic(
        data=[DemandePublic.model_validate(d) for d in demandes], count=count
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
    if not current_user.is_superuser and demande.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    return demande


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
    return create_demande(
        session=session, demande_in=demande_in, owner_id=current_user.id
    )


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
    if not current_user.is_superuser and demande.owner_id != current_user.id:
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
    return DemandePublic.model_validate(demande)


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
    if not current_user.is_superuser and demande.owner_id != current_user.id:
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
    if not current_user.is_superuser and demande.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    update_dict = demande_in.model_dump(exclude_unset=True)
    demande.sqlmodel_update(update_dict)
    session.add(demande)
    session.commit()
    session.refresh(demande)
    return demande


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
    if not current_user.is_superuser and demande.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    session.delete(demande)
    session.commit()
    return Message(message="Demande supprimée avec succès")
