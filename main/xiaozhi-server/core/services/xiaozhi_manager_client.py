import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from config.logger import setup_logging

TAG = __name__


class XiaozhiManagerClient:
    """Client for the external Admin Service.

    The Admin Service is the source of truth for runtime device config,
    chat sessions/messages, and session-level memory extraction jobs.
    """

    def __init__(self, config: Dict[str, Any], logger=None):
        manager_config = config.get("xiaozhi-manager", {}) or {}
        self.enabled = bool(manager_config.get("enabled", False) and manager_config.get("url"))
        self.base_url = str(manager_config.get("url", "")).rstrip("/")
        self.timeout = float(manager_config.get("timeout", 10))
        self.logger = logger or setup_logging()

    async def get_runtime_config(self, device_id: str) -> Dict[str, Any]:
        data = await self._post("devices/get-runtime-config", {"device_id": device_id})
        return data or {}

    async def update_runtime_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("devices/update-runtime-config", payload) or {}

    async def upsert_device(self, device_id: str, display_name: str = None, status: str = "active"):
        return await self._post(
            "devices/upsert",
            {
                "device_id": device_id,
                "display_name": display_name,
                "status": status,
            },
        )

    async def create_chat_session(
        self,
        session_id: str,
        device_id: str,
        source: str,
        client_id: str = None,
    ):
        return await self._post(
            "chat/sessions/create",
            {
                "session_id": session_id,
                "device_id": device_id,
                "source": source,
                "client_id": client_id,
                "started_at": self._now_iso(),
            },
        )

    async def end_chat_session(self, session_id: str, status: str = "completed"):
        return await self._post(
            "chat/sessions/end",
            {
                "session_id": session_id,
                "status": status,
                "ended_at": self._now_iso(),
            },
        )

    async def create_chat_message(
        self,
        message_id: str,
        session_id: str,
        device_id: str,
        role: str,
        content: str,
        sequence_no: int,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        return await self._post(
            "chat/messages/create",
            {
                "message_id": message_id,
                "session_id": session_id,
                "device_id": device_id,
                "role": role,
                "content": content,
                "status": status,
                "sequence_no": sequence_no,
                "created_at": self._now_iso(),
                "metadata": metadata or {},
            },
        )

    async def import_session_memory(self, device_id: str, session_id: str):
        return await self._post(
            "memory/session-import/import",
            {
                "device_id": device_id,
                "session_id": session_id,
            },
        )

    async def _post(self, path: str, payload: Dict[str, Any]):
        if not self.enabled:
            return None
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get("code") != 200:
                    self.logger.bind(tag=TAG).warning(
                        f"Admin Service返回非成功: {path}, {result}"
                    )
                    return None
                return result.get("data")
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"调用Admin Service失败: {path}, {e}")
            return None

    def run_from_thread(self, loop, coroutine, timeout: float = 5):
        if not self.enabled or loop is None:
            return None
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            self.logger.bind(tag=TAG).warning(f"等待Admin Service调用失败: {e}")
            return None

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat()

