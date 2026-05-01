# xiaozhi-server 最小语音机器人方案

本文记录当前已确定的 `xiaozhi-server` 部署与模型选型方案。目标是先实现一个简单稳定的语音聊天机器人，不启用智控台、设备管理、权限管理和复杂工具能力。

## 已确定选型

- VAD：使用默认本地 `SileroVAD`。
- ASR：使用阿里百炼流式 ASR，配置项为 `AliyunBLStreamASR`，模型使用 `fun-asr-realtime`。
- TTS：使用阿里百炼 TTS，配置项为 `AliBLTTS`，模型使用 `cosyvoice-v3-flash`，音色优先 `longhan_v3`，备选 `longanlang_v3`。
- 对话 LLM：使用阿里百炼千问模型，配置项为 `AliLLM`，走 OpenAI 兼容接口，模型使用 `qwen3.6-plus`。
- 长期记忆：使用 `PowerMem`，其中记忆抽取 LLM 和 Embedding 都使用阿里百炼模型(LLM: qwen3.5-flash, Embedding: text-embedding-v4)。
- 意图识别：关闭，使用 `nointent`。
- 配置方式：只运行 Python server，配置写入 `data/.config.yaml`，不启用 `manager-api`。

## 当前项目支持情况

当前代码已经支持以上方案，不需要新增 Provider：

- `core/providers/asr/aliyunbl_stream.py`：阿里百炼 Paraformer 实时流式 ASR。
- `core/providers/tts/alibl_stream.py`：阿里百炼 CosyVoice 流式 TTS。
- `core/providers/llm/openai/openai.py`：OpenAI 兼容 LLM，可用于阿里百炼千问。
- `core/providers/memory/powermem/powermem.py`：PowerMem 记忆保存与检索封装。
- `core/providers/vad/silero.py`：本地 Silero VAD。
- `core/providers/intent/nointent/nointent.py`：关闭意图识别。

关键遗漏项：没有发现必须补充的核心技术模块。上线前需要确认阿里百炼账号已开通对应模型服务，并准备好服务端公网/局域网可访问地址。

## 阿里百炼官方文档

- ASR `paraformer-realtime-v2`： [Paraformer 实时语音识别 WebSocket API](https://help.aliyun.com/zh/model-studio/websocket-for-paraformer-real-time-service)
- ASR `fun-asr-realtime`： [实时语音识别](https://help.aliyun.com/zh/model-studio/real-time-speech-recognition)
- TTS `cosyvoice-v2`： [CosyVoice 实时语音合成 API 参考](https://help.aliyun.com/zh/dashscope/developer-reference/cosyvoice-large-model-for-speech-synthesis/)
- TTS 音色列表： [CosyVoice 音色列表](https://www.alibabacloud.com/help/zh/model-studio/cosyvoice-voice-list)
- Embedding `text-embedding-v4`： [通用文本向量同步接口 API 详情](https://help.aliyun.com/zh/dashscope/developer-reference/text-embedding-api-details)
- Embedding 计费： [向量化计费说明](https://help.aliyun.com/zh/model-studio/developer-reference/billing-for-text-embedding)
- LLM Chat `qwen3.6-plus`： [文本生成](https://help.aliyun.com/document_detail/2712816.html)
- 模型规格与按量计费： [模型大全功能规格与计费](https://help.aliyun.com/document_detail/2840914.html)
- OpenAI 兼容接口： [如何通过 OpenAI 接口调用千问模型](https://help.aliyun.com/zh/dashscope/developer-reference/compatibility-of-openai-with-dashscope)
- API Key 获取入口： [阿里百炼控制台](https://bailian.console.aliyun.com/)

## 配置示例

以下内容建议写入 `main/xiaozhi-server/data/.config.yaml`。不要直接改 `config.yaml`，避免后续升级冲突。

```yaml
server:
  # Docker 或公网部署时建议显式填写设备可访问的地址
  websocket: ws://你的IP或域名:8000/xiaozhi/v1/
  vision_explain: http://你的IP或域名:8003/mcp/vision/explain

selected_module:
  VAD: SileroVAD
  ASR: AliyunBLStreamASR
  LLM: AliLLM
  TTS: AliBLTTS
  Memory: powermem
  Intent: nointent

ASR:
  AliyunBLStreamASR:
    type: aliyunbl_stream
    api_key: 你的阿里百炼API_KEY
    model: fun-asr-realtime
    format: pcm
    sample_rate: 16000
    output_dir: tmp/
    disfluency_removal_enabled: false
    semantic_punctuation_enabled: false
    max_sentence_silence: 200
    multi_threshold_mode_enabled: false
    punctuation_prediction_enabled: true
    inverse_text_normalization_enabled: true

LLM:
  AliLLM:
    type: openai
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    model_name: qwen3.6-plus
    api_key: 你的阿里百炼API_KEY
    temperature: 0.7
    max_tokens: 500
    top_p: 1
    frequency_penalty: 0

TTS:
  AliBLTTS:
    type: alibl_stream
    api_key: 你的阿里百炼API_KEY
    model: cosyvoice-v3-flash
    voice: longhan_v3
    output_dir: tmp/
    # format: pcm
    # volume: 50
    # rate: 1
    # pitch: 1

Memory:
  powermem:
    type: powermem
    enable_user_profile: false
    llm:
      provider: openai
      config:
        api_key: 你的阿里百炼API_KEY
        model: qwen3.5-flash
        openai_base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    embedder:
      provider: openai
      config:
        api_key: 你的阿里百炼API_KEY
        model: text-embedding-v4
        openai_base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    vector_store:
      provider: sqlite
      config: {}

Intent:
  nointent:
    type: nointent
```

## 使用备注

- `你的阿里百炼API_KEY` 可以先使用同一个百炼 API Key，统一从阿里云账号按量扣费。
- 需要在阿里百炼控制台确认 `fun-asr-realtime`、`cosyvoice-v3-flash`、`qwen3.6-plus`、`qwen3.5-flash`、`text-embedding-v4` 等模型已可用。
- PowerMem 的记忆抽取/总结模型推荐 `qwen3.5-flash`，比旧版 `qwen-flash` 更稳，成本又明显低于对话模型 `qwen3.6-plus`。
- `text-embedding-v4` 是百炼最新文本向量模型之一，成本较低，长期记忆向量化优先保持使用该模型。
- 如果希望降低对话 LLM 成本，可以把 `LLM.AliLLM.model_name` 从 `qwen3.6-plus` 改为 `qwen3.5-flash`。
- 如果后续要替换为 ChatGPT 或 Gemini，只需要新增或调整 `LLM` 配置，并修改 `selected_module.LLM`。
- 当前关闭 `Intent` 后，天气、新闻、音乐、IoT 控制等工具能力不会主动启用，更适合纯语音聊天机器人。
- VAD 是本地轻量模型，不需要 API Key。
- PowerMem 使用 SQLite 时不需要额外数据库；后续用户量变大再考虑 OceanBase 或 PostgreSQL。

## 后续 TODO

### 0. Web 端也复用小智 WebSocket 协议

Web 端不单独实现 HTTP Chat API，直接作为“浏览器里的虚拟小智设备”接入当前 `xiaozhi-server` WebSocket 协议。

最终结论：

- Web 端用户手动输入 `device-id`。
- WebSocket 连接时携带同一个 `device-id`。
- Web 端也发送 `hello`、`listen`、音频二进制包、`abort` 等小智协议消息。
- Web 端也接收 TTS 状态和音频包并播放。
- Web 端和硬件端使用同一个 `device-id` 时，长期记忆自然互通。
- Web 端和硬件端同时在线也允许存在，它们是独立 WebSocket 会话，但共享同一个设备身份和长期记忆。
- 可基于 `test/test_page.html` 改造成简单的“通话按钮”式 Web 页面。

后台管理系统只负责会话查询和未来配置管理，不直接提供对话服务。

建议数据库概念模型：

```text
sessions:
  session_id
  device_id
  source        # device / web
  client_id
  started_at
  ended_at
  status

messages:
  id
  session_id
  device_id
  role          # user / assistant
  content
  status        # completed / interrupted / failed
  sequence
  created_at
```

### 1. 打开历史上下文截断配置

当前代码中 `Dialogue.trim_history()` 已实现，但 `ConnectionHandler.chat()` 中默认未启用。后续需要增加配置项，例如：

```yaml
max_dialogue_turns: 10
```

并在每次请求 LLM 前保留最近 N 轮对话。长期事实交给 PowerMem，当前连接上下文只保留最近对话，降低 token 成本和延迟。

### 2. 独立聊天记录上报

不启用 `manager-api` 时，当前项目默认不会上报完整聊天记录。后续需要增加独立上报能力，将聊天记录写入自己的数据库。

推荐设计：

- 数据库中每条消息作为一条记录。
- 使用 `sessionId` 关联同一次 WebSocket 会话。
- 使用 `messageTime` 或自增序号排序。
- 记录 `deviceId`、`sessionId`、`role`、`content`、`messageTime`、`traceId/requestId` 等字段。
- 音频可以先不存，后续需要再加 `audioUrl` 或 `audioBase64`。

建议上报时机：

1. 接收到用户完整一段输入，并在提交 LLM 前，写入一条 `user` 消息。
2. LLM 本次流式回复结束并拼出完整文本后，写入一条 `assistant` 消息。

这个方案是合理的：它比“会话结束后一次性上报”更可靠，连接异常断开时也不会丢掉已完成的轮次；同时数据库可以按 `sessionId + messageTime` 还原完整会话。

实现上可基于现有 `core/handle/reportHandle.py` 和 `ConnectionHandler.report_queue` 改造，但需要去掉对 `manager-api` 的强依赖，新增本地配置：

```yaml
chat_report:
  enabled: true
  url: https://你的服务/api/chat-messages
  include_audio: false
```

### 3. 后台 per-device 配置能力

未来后台管理系统可以围绕 `device_id` 增加配置能力：

- 查看某个 `device_id` 的所有历史会话。
- 导入或编辑某个 `device_id` 的长期记忆。
- 设置某个 `device_id` 的 prompt / 人设。
- 未来按 `device_id` 定制模型配置、TTS 音色等。

短期先不实现动态配置加载，仍使用 `data/.config.yaml` 作为全局配置。

### 4. 微信聊天记录清洗与长期记忆导入

第一期需要支持从微信聊天记录、聊天截图或其他资料中导入长期记忆。短期采用 `PowerMem + SQLite`，不引入云端向量数据库。

推荐处理流程：

```text
微信聊天记录 / 聊天截图 / 其他资料
  -> 导出或 OCR
  -> 清洗成统一消息结构
  -> 按时间或轮次切分 chunk
  -> 去重、过滤无意义消息
  -> 调用 PowerMem add(messages=..., user_id=device_id)
  -> 写入本地 SQLite 长期记忆库
  -> 同步保存一份可后台查看的导入记录/记忆 item
```

可选工具：

- 微信聊天记录导出：`WeChatMsg`、`PyWxDump`。
- 聊天截图 OCR：`PaddleOCR`、阿里云 OCR，后续再用 LLM 整理成结构化消息。

导入建议：

- 不要一次性导入几万条原始消息。
- 每个 chunk 建议包含 20-50 条消息，或按一天/一段连续对话切分。
- 每个 chunk 记录 `device_id`、`source`、`time_range`、`import_batch_id`。
- 导入前过滤表情、撤回提示、无意义短句、重复消息等噪声。

计划新增接口：

```text
POST /api/memory/import
GET  /api/memory/list?device_id=xxx
GET  /api/memory/search?device_id=xxx&q=xxx
```

其中：

- `import`：接收清洗后的消息或文本 chunk，写入 PowerMem。
- `search`：走 PowerMem 相似度检索，用于验证实际对话时会召回哪些记忆。
- `list`：用于后台管理系统全量查看某个 `device_id` 的长期记忆。

后台全量查看长期记忆是必要能力，用于 debug 和记忆治理。虽然对话时只需要相似度检索相关记忆，但后台需要知道长期记忆库里到底有什么。因此需要额外维护可列表化的数据源。

建议额外维护业务表：

```text
memory_imports:
  id
  device_id
  source        # wechat / screenshot / manual / other
  raw_content
  normalized_content
  import_batch_id
  created_at

memory_items:
  id
  device_id
  content
  source
  source_time
  import_batch_id
  powermem_memory_id
  created_at
```

短期存储策略：

- PowerMem SQLite：负责向量检索和对话时召回。
- MySQL/业务数据库：负责后台展示、导入批次、原始资料、清洗后文本、记忆 item 列表。

这样即使 PowerMem Provider 主要暴露 `add/search`，后台仍可以通过业务表全量查看和管理长期记忆。

#### 长期记忆全量召回与治理

当前调研结论：

- PowerMem 官方能力包含 `add/search/update/delete`，CLI 也有 `list/get/delete-all` 一类操作。
- 当前 `xiaozhi-server` 的 `core/providers/memory/powermem/powermem.py` 只封装了 `add()` 和 `search()`。
- 因此第一期不要依赖 PowerMem Provider 做后台全量列表，后台全量查看以自己的业务表为准。

第一期实现策略：

1. 每次导入长期记忆时，先写入 PowerMem。
2. 从 PowerMem 返回结果中尽量提取 `memory_id`。
3. 同步写入业务库 `memory_items`，保存 `device_id`、`content`、`source`、`import_batch_id`、`powermem_memory_id`。
4. 后台全量列表查询 `memory_items`。
5. 对话召回调用 PowerMem `search()`。

修改/删除策略：

- 如果后台发现某条记忆有问题，先修改或删除 `memory_items`。
- 如果该记录保存了 `powermem_memory_id`，再同步调用 PowerMem 的 `update/delete`。
- 如果短期没有接入 PowerMem 的 `update/delete`，可以先把该条业务记录标记为 `deleted/disabled`，并在后续重建该 `device_id` 的 PowerMem 记忆索引时排除。

建议给 `memory_items` 增加状态字段：

```text
memory_items:
  status        # active / disabled / deleted
  updated_at
  deleted_at
```

中长期优化：

- 在本项目中扩展 PowerMem Provider，补充 `list_memories(device_id)`、`update_memory(memory_id, content)`、`delete_memory(memory_id)` 方法。
- 增加“按 device_id 重建长期记忆索引”的后台任务：从业务库 active 记忆重新写入 PowerMem，解决脏数据、误删、迁移等问题。

### 5. 回复打断能力确认

当前项目已实现服务端打断处理：

- 设备/客户端发送 `type=abort` 文本消息。
- 服务端进入 `core/handle/abortHandle.py`。
- 设置 `conn.client_abort = True`。
- 清理 TTS/上报/音频队列。
- 向设备发送 `{"type":"tts","state":"stop"}`。
- LLM 流式循环和 TTS 线程会检查 `client_abort` 并停止继续处理旧回复。

因此打断能力不是纯硬件内部功能，而是硬件/固件与服务端协同：

- 硬件/固件负责检测用户打断、发送 `abort` 消息。
- 服务端负责停止当前 LLM/TTS 流、清理队列、通知设备停止播放。

### 6. 未来可优化点

- `device-id` 暂时由 Web 用户手动输入；未来可增加 `device-id + access_code` 或 token，避免身份冒用。
- 后台可增加 `devices` 表，显式维护设备名称、备注、归属用户等元信息。
- 如果未来需要多用户体系，可以再增加 `user_id`，并建立 `user_id <-> device_id` 绑定关系。
- 长期记忆量变大后，可将 PowerMem 的向量存储从 SQLite 迁移到 OceanBase、PostgreSQL + pgvector 或专门向量数据库。
