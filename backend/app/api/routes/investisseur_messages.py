import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_user_from_token
from app.models import (
    InvestisseurConversationsPublic,
    InvestisseurMessage,
    InvestisseurMessageCreate,
    InvestisseurMessagePublic,
    InvestisseurMessagesPublic,
    Message,
    User,
)
from app.ws_manager import manager

router = APIRouter(prefix="/investisseurs", tags=["messages"])


def _get_investisseur(session: SessionDep, investisseur_id: uuid.UUID) -> User:
    user = session.get(User, investisseur_id)
    if not user or not user.is_investisseur:
        raise HTTPException(status_code=404, detail="Investisseur introuvable")
    return user


def _require_conversation_access(target: User, current_user: User) -> None:
    is_staff = current_user.is_superuser or current_user.is_admin
    if not is_staff and current_user.id != target.id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")


def _to_public(session: SessionDep, message: InvestisseurMessage) -> InvestisseurMessagePublic:
    sender = session.get(User, message.sender_id)
    sender_name = (sender.full_name or sender.email) if sender else "Utilisateur supprimé"
    return InvestisseurMessagePublic(
        id=message.id,
        investisseur_id=message.investisseur_id,
        sender_id=message.sender_id,
        sender_role=message.sender_role,
        sender_name=sender_name,
        contenu=message.contenu,
        created_at=message.created_at,
    )


@router.get("", response_model=InvestisseurConversationsPublic)
def read_conversations(session: SessionDep, current_user: CurrentUser) -> Any:
    if not (current_user.is_superuser or current_user.is_admin):
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    return InvestisseurConversationsPublic(
        data=crud.get_investisseur_conversations(session=session)
    )


@router.get("/{investisseur_id}/messages", response_model=InvestisseurMessagesPublic)
def read_messages(
    session: SessionDep, current_user: CurrentUser, investisseur_id: uuid.UUID
) -> Any:
    target = _get_investisseur(session, investisseur_id)
    _require_conversation_access(target, current_user)

    messages, count = crud.get_investisseur_messages(
        session=session, investisseur_id=investisseur_id
    )
    return InvestisseurMessagesPublic(
        data=[_to_public(session, m) for m in messages], count=count
    )


@router.post(
    "/{investisseur_id}/messages", response_model=InvestisseurMessagePublic, status_code=201
)
async def create_message_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    investisseur_id: uuid.UUID,
    message_in: InvestisseurMessageCreate,
) -> Any:
    target = _get_investisseur(session, investisseur_id)
    _require_conversation_access(target, current_user)

    is_admin_sender = current_user.is_superuser or current_user.is_admin
    message = crud.create_investisseur_message(
        session=session,
        investisseur_id=investisseur_id,
        sender=current_user,
        is_admin_sender=is_admin_sender,
        message_in=message_in,
    )
    public = _to_public(session, message)
    await manager.broadcast(investisseur_id, public.model_dump(mode="json"))
    return public


@router.post("/{investisseur_id}/messages/read", response_model=Message)
def mark_messages_read_route(
    session: SessionDep, current_user: CurrentUser, investisseur_id: uuid.UUID
) -> Any:
    target = _get_investisseur(session, investisseur_id)
    _require_conversation_access(target, current_user)

    is_admin_viewer = current_user.is_superuser or current_user.is_admin
    crud.mark_investisseur_messages_read(
        session=session, investisseur_id=investisseur_id, is_admin_viewer=is_admin_viewer
    )
    return Message(message="Messages marqués comme lus")


@router.websocket("/{investisseur_id}/messages/ws")
async def messages_ws(
    websocket: WebSocket,
    investisseur_id: uuid.UUID,
    token: str,
    session: SessionDep,
) -> None:
    """
    Receive-only channel, mirroring the demande chat socket: new messages are
    always created through the POST endpoint above, which broadcasts them to
    every open tab on this investor's conversation.
    """
    user = get_user_from_token(session, token)
    if not user:
        await websocket.close(code=4401)
        return

    target = session.get(User, investisseur_id)
    if not target or not target.is_investisseur:
        await websocket.close(code=4404)
        return
    if not (user.is_superuser or user.is_admin) and user.id != target.id:
        await websocket.close(code=4403)
        return

    await manager.connect(investisseur_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(investisseur_id, websocket)
