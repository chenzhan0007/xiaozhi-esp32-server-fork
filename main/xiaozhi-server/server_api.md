# xiaozhi-manager 后台管理/存储服务 API

本文档描述当前 `cz-cloud/backend` 中 `xiaozhi-manager` 模块的真实实现。

## 通用约定

- 路由根路径：`/xiaozhi-manager`
- 所有接口：`POST`
- 所有响应：`RequestResType<T>`
- 小智管理模块错误码：`31xxx`

成功响应：

```json
{
  "code": 200,
  "data": {}
}
```

失败响应：

```json
{
  "code": 31005,
  "msg": "小智微信聊天记录导入失败",
  "error": "具体错误"
}
```

## 错误码

```text
31000 XIAOZHI_MANAGER_UNKNOWN_ERROR
31001 XIAOZHI_CHAT_SESSION_NOT_FOUND
31002 XIAOZHI_IMPORT_BATCH_NOT_FOUND
31003 XIAOZHI_MEMORY_ITEM_NOT_FOUND
31004 XIAOZHI_IMPORT_SOURCE_NOT_SUPPORTED
31005 XIAOZHI_WECHAT_IMPORT_FAILED
```

## 数据库表

所有小智相关表都使用 `xiaozhi_` 前缀：

```text
xiaozhi_devices
xiaozhi_chat_sessions
xiaozhi_chat_messages
xiaozhi_memory_import_batches
xiaozhi_normalized_messages
xiaozhi_memory_items
xiaozhi_device_configs
```

`xiaozhi_style_profiles` 已移除。风格画像写入：

```text
xiaozhi_device_configs.style_prompt_fragment
xiaozhi_device_configs.style_profile_json
xiaozhi_device_configs.style_import_batch_id
xiaozhi_device_configs.style_updated_at
```

## 表结构摘要

### xiaozhi_devices

```text
id, device_id, display_name, status, last_seen_at, created_at, updated_at
```

### xiaozhi_chat_sessions

```text
id, session_id, device_id, source, client_id, status, started_at, ended_at, title, created_at, updated_at
```

### xiaozhi_chat_messages

```text
id, message_id, session_id, device_id, role, content, status, sequence_no, metadata, created_at
```

### xiaozhi_memory_import_batches

```text
id, import_batch_id, device_id, source_type, file_name, status, total_messages, total_chunks, total_memory_items, error_message, created_at, updated_at
```

### xiaozhi_normalized_messages

```text
id, message_id, import_batch_id, device_id, conversation_id, timestamp, sender_name, role, msg_type, content, raw_content, source, metadata, created_at
```

### xiaozhi_memory_items

```text
id, memory_item_id, device_id, content, memory_type, confidence, source, evidence_message_ids, import_batch_id, powermem_memory_id, metadata, created_at, updated_at
```

### xiaozhi_device_configs

```text
id, device_id, base_prompt, style_prompt_fragment, user_instructions, model_config, tts_config, memory_config, max_dialogue_turns, ai_persona_name, ai_persona_identity, ai_persona_relationship_with_user, style_profile_json, style_import_batch_id, style_updated_at, status, created_at, updated_at
```

## 设备接口

### POST /xiaozhi-manager/devices/upsert

```json
{
  "device_id": "device_xxx",
  "display_name": "客厅小包汤",
  "status": "active"
}
```

### POST /xiaozhi-manager/devices/list

```json
{
  "keyword": "客厅",
  "page": 1,
  "page_size": 20
}
```

### POST /xiaozhi-manager/devices/get-runtime-config

```json
{
  "device_id": "device_xxx"
}
```

### POST /xiaozhi-manager/devices/update-runtime-config

```json
{
  "device_id": "device_xxx",
  "base_prompt": "设备级基础 prompt",
  "style_prompt_fragment": "和用户说话时保持熟人感，句子偏短。",
  "user_instructions": [
    {
      "content": "每次回复开头先叫我的名字。",
      "priority": "high",
      "source": "manual",
      "status": "active"
    }
  ],
  "model_config": {},
  "tts_config": {},
  "memory_config": {},
  "max_dialogue_turns": 50,
  "ai_persona_name": "小包汤",
  "ai_persona_identity": "陪伴型语音助手",
  "ai_persona_relationship_with_user": "熟悉用户偏好的日常伙伴",
  "style_profile_json": {}
}
```

## 会话和消息接口

### POST /xiaozhi-manager/chat/sessions/create

```json
{
  "session_id": "session_uuid",
  "device_id": "device_xxx",
  "source": "device",
  "client_id": "web_test_client",
  "started_at": "2026-05-01T18:00:00+08:00"
}
```

### POST /xiaozhi-manager/chat/sessions/end

```json
{
  "session_id": "session_uuid",
  "status": "completed",
  "ended_at": "2026-05-01T18:05:00+08:00"
}
```

### POST /xiaozhi-manager/chat/sessions/list

```json
{
  "device_id": "device_xxx",
  "page": 1,
  "page_size": 20
}
```

### POST /xiaozhi-manager/chat/sessions/messages/list

```json
{
  "session_id": "session_uuid"
}
```

### POST /xiaozhi-manager/chat/messages/create

```json
{
  "message_id": "message_uuid",
  "session_id": "session_uuid",
  "device_id": "device_xxx",
  "role": "user",
  "content": "你好",
  "status": "completed",
  "sequence_no": 1,
  "created_at": "2026-05-01T18:00:01+08:00",
  "metadata": {}
}
```

### POST /xiaozhi-manager/chat/messages/batch

```json
{
  "messages": []
}
```

## 微信导入接口

前端先上传原始 CSV/JSON 到 COS，再把 URL 传给 background。

### POST /xiaozhi-manager/memory/wechat-import/import

```json
{
  "device_id": "device_xxx",
  "user_name": "我",
  "target_person_name": "张三",
  "source_type": "wechatmsg_csv_v1",
  "file_url": "https://cos.example.com/wechat.csv",
  "file_name": "wechat.csv"
}
```

支持的 `source_type`：

```text
wechatmsg_csv_v1
wechat_exporter_json_v1
```

导入流程：

```text
提交任务后立即返回 import_batch_id/status=processing
后台异步下载 file_url
  -> 解析 CSV/JSON
  -> 清洗、去噪、脱敏、去重
  -> 保存 xiaozhi_normalized_messages
  -> 3 天窗口 / 2 天步长 / 最大 300 条分段
  -> 调百炼 LLM 抽取 xiaozhi_memory_items
  -> 可选调用 Chat Service /api/memory/import-items 写入 PowerMem
  -> 回写 powermem_memory_id
  -> 调百炼 LLM 生成风格画像
  -> 更新 xiaozhi_device_configs
```

## 实时会话后处理

除微信导入外，实时聊天产生的历史会话也应由 background 作为业务真相源来做长期记忆抽取。

推荐职责边界：

```text
Chat Service
  -> 负责实时 WebSocket、ASR、LLM、TTS、PowerMem 检索
  -> 上报 chat session 和 chat messages 到 background
  -> 提供 PowerMem 写入/搜索/重建接口

background / xiaozhi-manager
  -> 保存完整会话和消息
  -> 在会话结束后或后台任务中读取 xiaozhi_chat_messages
  -> 调百炼 LLM 抽取长期记忆
  -> 写入 xiaozhi_memory_items
  -> 调 Chat Service 写入 PowerMem
  -> 回写 powermem_memory_id
```

不建议 Chat Service 在每轮对话里直接抽取长期记忆并写 PowerMem。原因：

- 长期记忆治理、编辑、删除、后台展示都以 background 业务库为中心。
- 运行时链路需要低延迟，不应被 LLM 记忆抽取阻塞。
- 同一套记忆抽取规则应同时服务微信导入和实时会话，避免两套分类/过滤逻辑分叉。
- background 能按完整 session 或多轮窗口做去重、过滤和审核，比单轮实时抽取更稳。

background 已实现会话记忆抽取任务接口：

```text
POST /xiaozhi-manager/memory/session-import/import
```

请求：

```json
{
  "device_id": "device_xxx",
  "session_id": "session_uuid"
}
```

响应：

```json
{
  "code": 200,
  "data": {
    "import_batch_id": "session_xxx",
    "status": "processing"
  }
}
```

该接口语义与微信导入一致：立即创建 `xiaozhi_memory_import_batches` 记录并返回，后台异步读取该 session 的消息、抽取记忆、写入业务库和 PowerMem。

批次字段：

```text
source_type = chat_session_v1
file_name = session_id
```

## 会话记忆导入接口

### POST /xiaozhi-manager/memory/session-import/import

```json
{
  "device_id": "device_xxx",
  "session_id": "session_uuid"
}
```

响应：

```json
{
  "code": 200,
  "data": {
    "import_batch_id": "session_xxx",
    "status": "processing"
  }
}
```

## 导入批次接口

### POST /xiaozhi-manager/memory/import-batches/create

```json
{
  "import_batch_id": "batch_uuid",
  "device_id": "device_xxx",
  "source_type": "wechatmsg_csv_v1",
  "file_name": "wechat.csv",
  "status": "processing"
}
```

### POST /xiaozhi-manager/memory/import-batches/update

```json
{
  "import_batch_id": "batch_uuid",
  "status": "completed",
  "total_messages": 1000,
  "total_chunks": 8,
  "total_memory_items": 36,
  "error_message": ""
}
```

### POST /xiaozhi-manager/memory/import-batches/list

```json
{
  "device_id": "device_xxx",
  "status": "completed",
  "page": 1,
  "page_size": 20
}
```

## 标准化消息接口

### POST /xiaozhi-manager/memory/normalized-messages/batch

```json
{
  "import_batch_id": "batch_uuid",
  "device_id": "device_xxx",
  "messages": []
}
```

### POST /xiaozhi-manager/memory/normalized-messages/list

```json
{
  "import_batch_id": "batch_uuid",
  "page": 1,
  "page_size": 100
}
```

## 长期记忆接口

### POST /xiaozhi-manager/memory/items/batch

```json
{
  "device_id": "device_xxx",
  "import_batch_id": "batch_uuid",
  "items": [
    {
      "memory_item_id": "mem_uuid",
      "content": "用户疲惫时更希望被简短陪伴。",
      "memory_type": "preference",
      "confidence": 0.86,
      "source": "wechat",
      "evidence_message_ids": ["wx_001"],
      "metadata": {}
    }
  ]
}
```

### POST /xiaozhi-manager/memory/items/list

```json
{
  "device_id": "device_xxx",
  "page": 1,
  "page_size": 50
}
```

### POST /xiaozhi-manager/memory/items/update

```json
{
  "memory_item_id": "mem_uuid",
  "content": "更新后的记忆内容"
}
```

### POST /xiaozhi-manager/memory/items/delete

```json
{
  "memory_item_id": "mem_uuid"
}
```

删除为物理删除：接口会直接删除 `xiaozhi_memory_items` 中对应记录。

## 百炼配置

微信导入链路中的记忆抽取和风格抽取使用 `backend/src/configs/alicloud.ts`：

```text
ALI_BAILIAN_API_KEY
ALI_BAILIAN_OPENAI_BASE_URL
xiaozhi-manager 内部默认模型 `qwen3.5-flash`
```

## Chat Service 同步

开发环境调用本地小智服务，生产环境地址暂时留空。

导入链路会使用 `backend/src/configs/xiaozhi.ts` 中的 `XIAOZHI_RUNTIME_BASE_URL` 调用：

```text
POST {XIAOZHI_RUNTIME_BASE_URL}/api/memory/import-items
```

如果该常量为空，导入仍会完成业务库保存，只是不写入 PowerMem。

## Chat Service 需要提供的接口

当前设计下，Python runtime / Chat Service 至少需要提供：

### 写入 PowerMem

```text
POST /api/memory/import-items
```

由 background 调用。输入为 background 已经抽取好的 `memory_items`，Chat Service 只负责写入 PowerMem 并返回 `powermem_memory_id`。

### 搜索 PowerMem

```text
GET /api/memory/search?device_id=xxx&q=xxx
POST /api/memory/clear
```

用于运行时召回，也可供后台调试记忆召回效果。

### 重建 PowerMem（建议补充）

```text
POST /api/memory/rebuild
```

建议请求：

```json
{
  "device_id": "device_xxx"
}
```

用于后台修改/删除大量记忆后，从 `xiaozhi_memory_items` 重新同步该设备的 PowerMem 索引。

### 获取运行时配置

Chat Service 作为客户端调用 background：

```text
POST /xiaozhi-manager/devices/get-runtime-config
```

运行时应读取并注入：

```text
base_prompt
ai_persona_card = style_prompt_fragment + user_instructions + ai_persona_* + style_profile_json
max_dialogue_turns
memory_config
model_config
tts_config
```

### 上报会话和消息

Chat Service 作为客户端调用 background：

```text
POST /xiaozhi-manager/chat/sessions/create
POST /xiaozhi-manager/chat/sessions/end
POST /xiaozhi-manager/chat/messages/create
POST /xiaozhi-manager/chat/messages/batch
```

上报策略：

- WebSocket 建立时创建 session。
- 用户完整输入进入 LLM 前，上报 `role=user`。
- assistant 回复完成后，上报 `role=assistant`。
- 连接结束时调用 session end。

## background 还需要补充的接口

当前 background 已实现微信导入、会话导入和基础管理接口。后续如果要增强会话任务管理，可以继续补充：

```text
POST /xiaozhi-manager/memory/session-import/retry
POST /xiaozhi-manager/memory/session-import/list
```

后续如果需要后台调试 PowerMem，还可以补充：

```text
POST /xiaozhi-manager/memory/powermem/search
POST /xiaozhi-manager/memory/powermem/rebuild
```

这两个接口由 background 转发到 Chat Service，便于后台统一调用入口。
