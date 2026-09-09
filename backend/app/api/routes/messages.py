import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_user_from_token
from app.models import (
    ChatMessage,
    ChatMessageCreate,
    ChatMessagePublic,
    ChatMessagesPublic,
    Demande,
    Message,
    User,
)
from app.ws_manager import manager

router = APIRouter(prefix="/demandes", tags=["messages"])


def _require_conversation_access(demande: Demande, user: User) -> None:
    if not (user.is_superuser or user.is_admin) and demande.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _to_public(session: SessionDep, message: ChatMessage) -> ChatMessagePublic:
    sender = session.get(User, message.sender_id)
    sender_name = (sender.full_name or sender.email) if sender else "Utilisateur supprimé"
    return ChatMessagePublic(
        id=message.id,
        demande_id=message.demande_id,
        sender_id=message.sender_id,
        sender_role=message.sender_role,
        sender_name=sender_name,
        contenu=message.contenu,
        created_at=message.created_at,
    )


@router.get("/{demande_id}/messages", response_model=ChatMessagesPublic)
def read_messages(session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID) -> Any:
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    _require_conversation_access(demande, current_user)

    messages, count = crud.get_messages(session=session, demande_id=demande_id)
    return ChatMessagesPublic(
        data=[_to_public(session, m) for m in messages], count=count
    )


@router.post("/{demande_id}/messages", response_model=ChatMessagePublic, status_code=201)
async def create_message_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    demande_id: uuid.UUID,
    message_in: ChatMessageCreate,
) -> Any:
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    _require_conversation_access(demande, current_user)

    is_admin_sender = current_user.is_superuser or current_user.is_admin
    message = crud.create_message(
        session=session,
        demande_id=demande_id,
        sender=current_user,
        is_admin_sender=is_admin_sender,
        message_in=message_in,
    )
    public = _to_public(session, message)
    await manager.broadcast(demande_id, public.model_dump(mode="json"))
    return public


@router.post("/{demande_id}/messages/read", response_model=Message)
def mark_messages_read_route(
    session: SessionDep, current_user: CurrentUser, demande_id: uuid.UUID
) -> Any:
    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    _require_conversation_access(demande, current_user)

    is_admin_viewer = current_user.is_superuser or current_user.is_admin
    crud.mark_messages_read(
        session=session, demande_id=demande_id, is_admin_viewer=is_admin_viewer
    )
    return Message(message="Messages marqués comme lus")


@router.websocket("/{demande_id}/messages/ws")
async def messages_ws(
    websocket: WebSocket,
    demande_id: uuid.UUID,
    token: str,
    session: SessionDep,
) -> None:
    """
    Receive-only channel: a client that connects here just gets pushed new
    ChatMessagePublic payloads as they're created via the POST endpoint above.
    Sending a message always goes through POST, never through this socket.
    """
    user = get_user_from_token(session, token)
    if not user:
        await websocket.close(code=4401)
        return

    demande = crud.get_demande(session=session, demande_id=demande_id)
    if not demande:
        await websocket.close(code=4404)
        return
    if not (user.is_superuser or user.is_admin) and demande.owner_id != user.id:
        await websocket.close(code=4403)
        return

    await manager.connect(demande_id, websocket)
    try:
        while True:
            # We don't act on incoming frames — this just keeps the connection
            # alive and lets us detect disconnects via WebSocketDisconnect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(demande_id, websocket)
