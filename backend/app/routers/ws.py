import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.broadcaster import manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep connection alive, ignore client messages
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
