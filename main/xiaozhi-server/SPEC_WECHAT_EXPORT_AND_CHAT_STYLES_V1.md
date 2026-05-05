# 微信聊天记录导入、长期记忆与聊天风格化方案

本文档描述当前 background 服务中的微信导入闭环实现。虽然文件名仍保留 V1，内容已按当前实现更新。

## 核心结论

- 微信聊天记录导入、解析、清洗、分段、LLM 抽取和业务库存储都在 `cz-cloud/backend` 的 `xiaozhi-manager` 模块完成。
- 小智 Python 服务不处理微信原始文件，只负责实时聊天和 PowerMem 写入/检索。
- 前端先把 CSV/JSON 文件上传到 COS，再把 `file_url` 提交给 background 导入接口。
- 风格画像不再使用独立 `style_profiles` 表，而是合并到 `xiaozhi_device_configs`。

## 服务职责

### background / Admin Service

- 接收 COS 文件 URL。
- 下载 WeChatMsg CSV 或 wechat-exporter JSON。
- 解析为统一标准消息。
- 清洗、去噪、脱敏、去重。
- 使用 3 天窗口、2 天步长分段。
- 调用百炼 LLM 抽取长期记忆。
- 调用百炼 LLM 生成风格画像。
- 保存 `xiaozhi_memory_import_batches`、`xiaozhi_normalized_messages`、`xiaozhi_memory_items`。
- 更新 `xiaozhi_device_configs` 中的当前生效风格配置。
- 可选调用小智 Python 服务写入 PowerMem。

### xiaozhi Python / Chat Service

- 负责 WebSocket 实时语音聊天。
- 负责 ASR / LLM / TTS。
- 负责 PowerMem 写入和搜索。
- 运行时调用 background 的 runtime config 接口获取当前设备配置。
- 将实时聊天会话和消息上报给 background。

## 身份模型

第一阶段统一使用 `device_id`：

```text
硬件设备：device_id = 固件上报 device-id
Web 测试端：用户手动输入 device_id
PowerMem：user_id = device_id
后台数据：按 device_id 聚合
运行时配置：每个 device_id 一条 xiaozhi_device_configs
```

## 支持格式

当前支持：

```text
wechatmsg_csv_v1
wechat_exporter_json_v1
```

暂不支持：

```text
截图 OCR
语音消息转写
动态 Style Controller
LoRA / SFT 微调
云端向量数据库
```

## 标准消息结构

不同导出格式会统一成标准消息，并保存到 `xiaozhi_normalized_messages`：

```json
{
  "message_id": "wx_000001",
  "import_batch_id": "wechat_xxx",
  "device_id": "device_xxx",
  "conversation_id": "contact_or_group_id",
  "timestamp": "2025-01-18T21:35:22+08:00",
  "sender_name": "张三",
  "role": "target",
  "msg_type": "text",
  "content": "清洗后的文本",
  "raw_content": "原始文本",
  "source": "wechat",
  "metadata": {
    "export_tool": "WeChatMsg"
  }
}
```

`role`：

```text
user      用户自己
target    目标风格对象
other     群聊其他人
system    系统消息
```

## 清洗规则

background 会执行：

- 删除撤回提示、系统通知。
- 删除空消息、重复消息。
- 删除纯媒体占位符，如 `[图片]`、`[视频]`、`[文件]`。
- 过滤低价值单字短消息，如“嗯”“哦”“好”。
- 删除 HTML 标签和零宽字符。
- 脱敏手机号、证件号、长数字串。

## 分段策略

当前实现：

```text
聊天日边界：凌晨 04:00
窗口长度：3 天
滑动步长：2 天
单 chunk 最大消息数：300
```

示例：

```text
chunk_1: 第 1 天 04:00 -> 第 4 天 04:00
chunk_2: 第 3 天 04:00 -> 第 6 天 04:00
chunk_3: 第 5 天 04:00 -> 第 8 天 04:00
```

## 记忆抽取

background 调用百炼 OpenAI 兼容接口，模型配置位于：

```text
backend/src/configs/alicloud.ts
```

使用：

```text
ALI_BAILIAN_API_KEY
ALI_BAILIAN_OPENAI_BASE_URL
xiaozhi-manager 内部默认模型 `qwen3.5-flash`
```

LLM 输出会被解析为：

```json
[
  {
    "memory_type": "preference",
    "content": "用户疲惫时更希望被简短陪伴，而不是立刻收到大量建议。",
    "confidence": 0.86,
    "evidence_message_ids": ["wx_001", "wx_018"],
    "subject": "user",
    "related_person": "target_person",
    "privacy_level": "private"
  }
]
```

过滤规则：

- `confidence < 0.65` 不写入。
- 没有 `content` 不写入。
- 没有 `evidence_message_ids` 不写入。
- 按 `device_id + memory_type + subject + content` 去重。

最终保存到 `xiaozhi_memory_items`。

## 风格抽取

风格抽取只分析 `role=target` 且 `msg_type=text` 的消息，最多取前 800 条样本。

LLM 输出：

```json
{
  "profile_json": {
    "tone": ["自然", "熟人感"],
    "sentence_length": "short_to_medium",
    "comfort_style": "先接住情绪，少分析，不连续追问"
  },
  "prompt_fragment": "和用户说话时保持熟人感，句子偏短，语气自然。"
}
```

保存位置：

```text
xiaozhi_device_configs.style_prompt_fragment
xiaozhi_device_configs.style_profile_json
xiaozhi_device_configs.style_import_batch_id
xiaozhi_device_configs.style_updated_at
```

## 用户长期指令

用户后续提出的长期要求不要混入风格画像，应保存到：

```text
xiaozhi_device_configs.user_instructions
```

示例：

```json
[
  {
    "content": "每次回复开头先叫我的名字。",
    "priority": "high",
    "source": "manual",
    "status": "active"
  }
]
```

## 导入接口

所有接口都遵循当前项目规范：

```text
POST
RequestResType<T>
/xiaozhi-manager
```

微信导入入口：

```text
POST /xiaozhi-manager/memory/wechat-import/import
```

请求：

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

响应：

```json
{
  "code": 200,
  "data": {
    "import_batch_id": "wechat_xxx",
    "status": "processing"
  }
}
```

## 导入流程

```text
前端上传 CSV/JSON 到 COS
  -> 前端把 file_url 提交给 background
  -> background 创建 xiaozhi_memory_import_batches
  -> background 立即返回 import_batch_id/status=processing
  -> background 异步下载文件
  -> background 解析、清洗、保存 xiaozhi_normalized_messages
  -> background 分段
  -> background 调百炼 LLM 抽取 xiaozhi_memory_items
  -> background 可选调用 Chat Service 写入 PowerMem
  -> background 回写 powermem_memory_id
  -> background 调百炼 LLM 生成风格画像
  -> background 更新 xiaozhi_device_configs
```

## 运行时聊天流程

```text
设备/Web 连接 Chat Service
  -> Chat Service 获取 device_id
  -> Chat Service 调 background /xiaozhi-manager/devices/get-runtime-config
  -> Chat Service 注入 base_prompt/style_prompt_fragment/user_instructions
  -> Chat Service 搜索 PowerMem
  -> Chat Service 调 LLM/TTS
  -> Chat Service 上报会话和消息到 background
```

## 实时会话长期记忆抽取

微信导入只是离线资料导入的一种来源。实时聊天本身也会持续产生高价值长期记忆。

第一性原则上，长期记忆应该以 background 业务库为真相源：

- background 已经保存完整会话和消息。
- 后台管理、编辑、删除、审核都发生在 background。
- 记忆抽取规则应该和微信导入共用同一套分类、过滤、去重逻辑。
- Chat Service 的实时链路应该尽量轻，不应把 LLM 记忆抽取放在每轮对话主路径上。

因此实时聊天的推荐链路是：

```text
Chat Service 建立 WebSocket
  -> background 创建 xiaozhi_chat_sessions
用户输入
  -> Chat Service 上报 xiaozhi_chat_messages(role=user)
助手回复完成
  -> Chat Service 上报 xiaozhi_chat_messages(role=assistant)
会话结束
  -> Chat Service 结束 xiaozhi_chat_sessions
  -> background 异步读取该 session 的完整消息
  -> background 调百炼 LLM 抽取 memory_items
  -> background 写入 xiaozhi_memory_items
  -> background 调 Chat Service /api/memory/import-items 写入 PowerMem
  -> background 回写 powermem_memory_id
```

不建议 Chat Service 直接抽取长期记忆：

- 它会增加实时响应路径压力。
- 直接写 PowerMem 会绕过 background 的业务表，后续后台无法完整治理。
- 微信导入和实时会话会产生两套抽取逻辑，容易漂移。

### 会话记忆导入接口

background 已实现：

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

该接口会创建 `xiaozhi_memory_import_batches`，并使用：

```text
source_type = chat_session_v1
```

### Chat Service 接口职责

Chat Service 需要保留或补充以下能力：

```text
POST /api/memory/import-items
GET  /api/memory/search?device_id=xxx&q=xxx
POST /api/memory/rebuild
```

其中：

- `import-items`：只接收 background 已抽取好的记忆并写入 PowerMem。
- `search`：运行时召回和后台调试召回使用。
- `clear`：清空某个 device_id 在 Runtime PowerMem 中的全部记忆。
- `rebuild`：从 background 的业务库重建某个 device_id 的 PowerMem 索引。

Chat Service 作为客户端还需要调用 background：

```text
POST /xiaozhi-manager/devices/get-runtime-config
POST /xiaozhi-manager/chat/sessions/create
POST /xiaozhi-manager/chat/sessions/end
POST /xiaozhi-manager/chat/messages/create
POST /xiaozhi-manager/chat/messages/batch
```

## 相关表

当前表名：

```text
xiaozhi_devices
xiaozhi_chat_sessions
xiaozhi_chat_messages
xiaozhi_memory_import_batches
xiaozhi_normalized_messages
xiaozhi_memory_items
xiaozhi_device_configs
```

不再使用：

```text
xiaozhi_style_profiles
```
