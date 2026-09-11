import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_user_from_token
from app.models import (
    Message,
    MessagerieConversationsPublic,
    User,
    UserMessage,
    UserMessageCreate,
    UserMessagePublic,
    UserMessagesPublic,
)
from app.ws_manager import manager

router = APIRouter(prefix="/messagerie", tags=["messages"])


def _require_staff(current_user: User) -> None:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _require_conversation_access(target: User, current_user: User) -> None:
    is_staff = current_user.is_superuser or current_user.is_admin
    if not is_staff and current_user.id != target.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _to_public(session: SessionDep, message: UserMessage) -> UserMessagePublic:
    sender = session.get(User, message.sender_id)
    sender_name = (sender.full_name or sender.email) if sender else "Utilisateur supprimé"
    return UserMessagePublic(
        id=message.id,
        user_id=message.user_id,
        sender_id=message.sender_id,
        sender_role=message.sender_role,
        sender_name=sender_name,
        contenu=message.contenu,
        created_at=message.created_at,
    )


@router.get("/conversations", response_model=MessagerieConversationsPublic)
def read_conversations(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Boîte de réception unifiée admin : un utilisateur par ligne, quel que
    soit son rôle — la conversation pointée est celle du dossier de crédit
    pour un client, celle du canal générique ci-dessous pour un
    investisseur/admin.
    """
    _require_staff(current_user)
    data = crud.get_messagerie_conversations(session=session, exclude_user_id=current_user.id)
    return MessagerieConversationsPublic(data=data)


@router.get("/{user_id}/messages", response_model=UserMessagesPublic)
def read_messages(session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID) -> Any:
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    _require_conversation_access(target, current_user)

    messages, count = crud.get_user_messages(session=session, user_id=user_id)
    return UserMessagesPublic(data=[_to_public(session, m) for m in messages], count=count)


@router.post("/{user_id}/messages", response_model=UserMessagePublic, status_code=201)
async def create_message_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    message_in: UserMessageCreate,
) -> Any:
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    _require_conversation_access(target, current_user)

    is_admin_sender = current_user.is_superuser or current_user.is_admin
    message = crud.create_user_message(
        session=session,
        user_id=user_id,
        sender=current_user,
        is_admin_sender=is_admin_sender,
        message_in=message_in,
    )
    public = _to_public(session, message)
    await manager.broadcast(user_id, public.model_dump(mode="json"))
    return public


@router.post("/{user_id}/messages/read", response_model=Message)
def mark_messages_read_route(
    session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID
) -> Any:
    target = session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    _require_conversation_access(target, current_user)

    is_admin_viewer = current_user.is_superuser or current_user.is_admin
    crud.mark_user_messages_read(session=session, user_id=user_id, is_admin_viewer=is_admin_viewer)
    return Message(message="Messages marqués comme lus")


@router.websocket("/{user_id}/messages/ws")
async def messages_ws(
    websocket: WebSocket,
    user_id: uuid.UUID,
    token: str,
    session: SessionDep,
) -> None:
    """
    Receive-only channel, mirroring the demande chat socket: new messages are
    always created through the POST endpoint above, which broadcasts them to
    every open tab on this conversation.
    """
    user = get_user_from_token(session, token)
    if not user:
        await websocket.close(code=4401)
        return

    target = session.get(User, user_id)
    if not target:
        await websocket.close(code=4404)
        return
    if not (user.is_superuser or user.is_admin) and user.id != target.id:
        await websocket.close(code=4403)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user_id, websocket)
