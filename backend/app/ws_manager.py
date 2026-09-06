import uuid
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """
    In-memory registry of open WebSocket connections, grouped by demande_id.
    A single backend process is enough for this app's scale — no Redis/pub-sub
    needed. Connections are receive-only from the client's perspective;
    sending a chat message always goes through the REST POST endpoint, which
    calls `broadcast` after persisting so every open tab gets the update.
    """

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, list[WebSocket]] = {}

    async def connect(self, demande_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(demande_id, []).append(websocket)

    def disconnect(self, demande_id: uuid.UUID, websocket: WebSocket) -> None:
        sockets = self._connections.get(demande_id)
        if not sockets:
            return
        if websocket in sockets:
            sockets.remove(websocket)
        if not sockets:
            self._connections.pop(demande_id, None)

    async def broadcast(self, demande_id: uuid.UUID, payload: dict[str, Any]) -> None:
        sockets = list(self._connections.get(demande_id, []))
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                self.disconnect(demande_id, socket)


manager = ConnectionManager()
