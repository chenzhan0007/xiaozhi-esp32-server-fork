import json
from aiohttp import web

from core.api.base_handler import BaseHandler
from core.services.power_memory_runtime import PowerMemoryRuntimeService


class MemoryHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        self.service = PowerMemoryRuntimeService(config)

    async def clear(self, request):
        response = None
        try:
            data = await request.json()
            device_id = data.get("device_id", "").strip()
            if not device_id:
                raise ValueError("device_id 不能为空")
            response = self._json({"success": True, "data": await self.service.clear(device_id)})
        except Exception as e:
            self.logger.bind(tag=__name__).error(f"清空记忆失败: {e}")
            response = self._json({"success": False, "message": str(e)}, status=400)
        finally:
            self._add_cors_headers(response)
            return response

    async def import_items(self, request):
        response = None
        try:
            data = await request.json()
            device_id = data.get("device_id", "").strip()
            import_batch_id = data.get("import_batch_id", "").strip() or "manual"
            items = data.get("items", [])
            if not device_id or not isinstance(items, list):
                raise ValueError("device_id 和 items 均不能为空")
            for item in items:
                if isinstance(item, dict):
                    item.setdefault("import_batch_id", import_batch_id)
            result = await self.service.import_items(device_id, items)
            response = self._json({"success": True, "data": result})
        except Exception as e:
            self.logger.bind(tag=__name__).error(f"记忆条目导入失败: {e}")
            response = self._json({"success": False, "message": str(e)}, status=400)
        finally:
            self._add_cors_headers(response)
            return response

    async def search(self, request):
        response = None
        try:
            device_id = request.query.get("device_id", "").strip()
            query = request.query.get("q", "").strip()
            top_k = request.query.get("top_k") or request.query.get("search_limit")
            score_threshold = request.query.get("score_threshold")
            if not device_id or not query:
                raise ValueError("device_id 和 q 不能为空")
            response = self._json({
                "success": True,
                "data": await self.service.search(
                    device_id,
                    query,
                    search_limit=int(top_k) if top_k else None,
                    score_threshold=float(score_threshold) if score_threshold else None,
                ),
            })
        except Exception as e:
            response = self._json({"success": False, "message": str(e)}, status=400)
        finally:
            self._add_cors_headers(response)
            return response

    def _json(self, payload, status: int = 200):
        return web.Response(
            text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            content_type="application/json",
            status=status,
        )

