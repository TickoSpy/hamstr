import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)

    async def broadcast(self, data: dict[str, Any]) -> None:
        if not self._active:
            return
        message = json.dumps(data)
        dead: set[WebSocket] = set()
        for ws in list(self._active):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self._active -= dead


manager = ConnectionManager()
