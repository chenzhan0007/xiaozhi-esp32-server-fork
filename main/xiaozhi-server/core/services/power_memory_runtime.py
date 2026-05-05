import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.logger import setup_logging
from core.utils import memory as memory_utils
from core.utils.power_memory_config import (
    DEFAULT_POWER_MEMORY_SCORE_THRESHOLD,
    DEFAULT_POWER_MEMORY_SEARCH_LIMIT,
)

TAG = __name__


@dataclass
class RuntimeMemoryItem:
    content: str
    memory_type: str = "preference"
    confidence: float = 1.0
    evidence_message_ids: List[str] = field(default_factory=list)
    source: str = "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)
    memory_item_id: Optional[str] = None
    powermem_memory_id: Optional[str] = None
    import_batch_id: Optional[str] = None

    def to_response(self) -> Dict[str, Any]:
        return {
            "memory_item_id": self.memory_item_id,
            "content": self.content,
            "memory_type": self.memory_type,
            "confidence": self.confidence,
            "source": self.source,
            "evidence_message_ids": self.evidence_message_ids,
            "metadata": self.metadata,
            "import_batch_id": self.import_batch_id,
            "powermem_memory_id": self.powermem_memory_id,
        }


class PowerMemoryRuntimeService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = setup_logging()
        memory_config = self.config.get("Memory", {}).get(
            self.config.get("selected_module", {}).get("Memory", ""),
            {},
        )
        self.search_limit = int(
            memory_config.get("search_limit")
            or memory_config.get("top_k")
            or DEFAULT_POWER_MEMORY_SEARCH_LIMIT
        )
        self.score_threshold = float(
            memory_config.get("score_threshold") or DEFAULT_POWER_MEMORY_SCORE_THRESHOLD
        )

    async def clear(self, device_id: str) -> Dict[str, Any]:
        provider = self._provider(device_id)
        result = await self._clear(provider, device_id)
        return {"device_id": device_id, "result": result}

    async def import_items(self, device_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        runtime_items = [self._to_item(item) for item in items if str(item.get("content", "")).strip()]
        provider = self._provider(device_id)
        for item in runtime_items:
            self.logger.bind(tag=TAG).info(
                f"PowerMem写入记忆: device_id={device_id}, memory_item_id={item.memory_item_id}, infer=False, content={item.content}"
            )
            result = await self._add(provider, device_id, item)
            item.powermem_memory_id = self._extract_memory_id(result)
        return {"items": [item.to_response() for item in runtime_items]}

    async def search(
        self,
        device_id: str,
        query: str,
        search_limit: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        effective_search_limit = search_limit or self.search_limit
        effective_score_threshold = (
            self.score_threshold if score_threshold is None else score_threshold
        )
        provider = self._provider(device_id)
        self.logger.bind(tag=TAG).info(
            f"PowerMem搜索开始: device_id={device_id}, query={query}, limit={effective_search_limit}, score_threshold={effective_score_threshold}"
        )
        raw_results = await self._raw_search(
            provider,
            device_id,
            query,
            effective_search_limit,
        )
        self.logger.bind(tag=TAG).info(
            f"PowerMem原始搜索结果: device_id={device_id}, results={raw_results}"
        )
        filtered_results = self._filter_search_results(
            raw_results,
            effective_score_threshold,
        )
        formatted_result = self._format_search_results(filtered_results)
        self.logger.bind(tag=TAG).info(
            f"PowerMem格式化搜索结果: device_id={device_id}, result={formatted_result or '<empty>'}"
        )
        return {
            "device_id": device_id,
            "query": query,
            "result": formatted_result,
            "results": filtered_results,
            "raw_results": raw_results,
            "search_limit": effective_search_limit,
            "score_threshold": effective_score_threshold,
        }

    def _provider(self, device_id: str):
        selected = self.config.get("selected_module", {}).get("Memory")
        memory_config = self.config.get("Memory", {}).get(selected, {})
        memory_type = memory_config.get("type", selected)
        provider = memory_utils.create_instance(
            memory_type, memory_config, self.config.get("summaryMemory")
        )
        provider.init_memory(
            role_id=device_id,
            llm=None,
            summary_memory=self.config.get("summaryMemory"),
            save_to_file=False,
        )
        return provider

    async def _add(self, provider, device_id: str, item: RuntimeMemoryItem):
        if not getattr(provider, "memory_client", None):
            return None
        metadata = {
            "memory_item_id": item.memory_item_id,
            "memory_type": item.memory_type,
            "confidence": item.confidence,
            "source": item.source,
            "evidence_message_ids": item.evidence_message_ids,
            **(item.metadata or {}),
        }
        try:
            result = provider.memory_client.add(
                messages=item.content,
                user_id=device_id,
                metadata=metadata,
                infer=False,
            )
        except TypeError:
            self.logger.bind(tag=TAG).warning(
                "当前PowerMem版本不支持infer参数，可能会触发二次LLM抽取"
            )
            result = provider.memory_client.add(
                messages=item.content,
                user_id=device_id,
                metadata=metadata,
            )
        if asyncio.iscoroutine(result):
            result = await result
        return result

    async def _clear(self, provider, device_id: str):
        memory_client = getattr(provider, "memory_client", None)
        if memory_client is None:
            raise RuntimeError("PowerMem memory_client 为空")

        # PowerMem / Mem0 风格 SDK 在不同版本中清空接口签名可能不同，
        # 这里按最严格的 device_id/user_id 维度逐个尝试，避免误删其他设备。
        attempts = (
            ("delete_all", {"user_id": device_id}),
            ("delete_all", {"filters": {"user_id": device_id}}),
            ("delete_all_memories", {"user_id": device_id}),
            ("reset", {"user_id": device_id}),
        )
        last_error = None
        for method_name, kwargs in attempts:
            method = getattr(memory_client, method_name, None)
            if not method:
                continue
            try:
                result = method(**kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                self.logger.bind(tag=TAG).info(
                    f"PowerMem清空成功: device_id={device_id}, method={method_name}"
                )
                return result if result is not None else {"success": True, "method": method_name}
            except TypeError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(f"当前 PowerMem SDK 不支持按 device_id 清空记忆: {last_error}")

    def _to_item(self, raw: Dict[str, Any]) -> RuntimeMemoryItem:
        evidence_message_ids = raw.get("evidence_message_ids") or []
        return RuntimeMemoryItem(
            memory_item_id=raw.get("memory_item_id"),
            content=str(raw.get("content", "")).strip(),
            memory_type=str(raw.get("memory_type", "preference")),
            confidence=float(raw.get("confidence", 1)),
            evidence_message_ids=[str(value) for value in evidence_message_ids],
            source=str(raw.get("source", "manual")),
            metadata=raw.get("metadata", {}) if isinstance(raw.get("metadata", {}), dict) else {},
            import_batch_id=raw.get("import_batch_id"),
        )

    def _extract_memory_id(self, result) -> Optional[str]:
        if not isinstance(result, dict):
            return None
        for key in ("id", "memory_id"):
            if result.get(key):
                return str(result[key])
        results = result.get("results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                for key in ("id", "memory_id"):
                    if first.get(key):
                        return str(first[key])
        return None

    async def _raw_search(self, provider, device_id: str, query: str, limit: int):
        memory_client = getattr(provider, "memory_client", None)
        if memory_client is None:
            self.logger.bind(tag=TAG).warning("PowerMem搜索失败: memory_client为空")
            return None
        try:
            result = memory_client.search(query=query, user_id=device_id, limit=limit)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            self.logger.bind(tag=TAG).error(
                f"PowerMem原始搜索异常: device_id={device_id}, query={query}, error={e}"
            )
            return None

    def _filter_search_results(self, raw_results, score_threshold: float) -> List[Dict[str, Any]]:
        if not isinstance(raw_results, dict):
            return []
        result_items = raw_results.get("results")
        if not isinstance(result_items, list):
            return []
        filtered_items = []
        for entry in result_items:
            if not isinstance(entry, dict):
                continue
            score = entry.get("score")
            if score is None:
                filtered_items.append(entry)
                continue
            try:
                if float(score) >= score_threshold:
                    filtered_items.append(entry)
            except (TypeError, ValueError):
                continue
        return filtered_items

    def _format_search_results(self, result_items: List[Dict[str, Any]]) -> str:
        memories = []
        for entry in result_items:
            if not isinstance(entry, dict):
                continue
            memory = entry.get("memory") or entry.get("content") or entry.get("text")
            if not memory:
                continue
            score = entry.get("score")
            score_text = ""
            if isinstance(score, (int, float)):
                score_text = f" (score={score:.3f})"
            timestamp = entry.get("updated_at") or entry.get("created_at") or ""
            if timestamp and isinstance(timestamp, str):
                timestamp = timestamp.split(".")[0].replace("T", " ")
                memories.append(f"[{timestamp}] {memory}{score_text}")
            else:
                memories.append(f"{memory}{score_text}")
        if not memories:
            return ""
        return "【相关记忆】\n" + "\n".join(f"- {memory}" for memory in memories)

