# xiaozhi-server 服务说明

`xiaozhi-server` 是 `xiaozhi-esp32-server` 项目的核心 Python 服务，负责与小智 ESP32 设备建立实时通信，完成语音输入接收、VAD、ASR、LLM、TTS、工具调用、OTA 地址下发、视觉分析等运行时能力。

如果你的需求只是让设备连接自己的服务器，并完成“语音输入 -> 识别 -> 大模型回复 -> 语音合成 -> 回传播放”的闭环，通常只需要部署本目录下的 Python 服务，不需要 `manager-api`、`manager-web`、`manager-mobile`。

## 核心职责

- 启动 WebSocket 服务，接收 ESP32 设备连接和音频流。
- 启动 HTTP 服务，提供简单 OTA 接口和视觉分析接口。
- 根据 `config.yaml` 与 `data/.config.yaml` 初始化 VAD、ASR、LLM、TTS、Intent、Memory、VLLM 等模块。
- 处理设备文本消息，例如 `hello`、`listen`、`abort`、`iot`、`mcp`、`ping`、`server`。
- 将设备上传的 Opus/PCM 音频转换为文本，再将大模型输出切分并合成为 Opus 音频下发给设备。
- 支持插件、设备 IoT、设备 MCP、服务端 MCP、MCP 接入点等工具调用能力。
- 在启用智控台模式时，可从 `manager-api` 拉取公共配置和设备私有配置。

## 目录结构

```text
xiaozhi-server/
  app.py                         # 服务入口，启动 WebSocket、HTTP/OTA、GC 管理等任务
  config.yaml                    # 默认配置，不建议直接放密钥
  config_from_api.yaml           # 接入 manager-api 时的配置模板
  docker-compose.yml             # 只运行 Python server 的 Docker Compose
  docker-compose_all.yml         # 全模块部署相关 compose
  requirements.txt               # Python 依赖，推荐 Python 3.10
  performance_tester.py          # 模型性能测试入口
  mcp_server_settings.json       # 服务端 MCP 配置
  data/                          # 用户配置、运行数据、OTA bin 等，部署时通常挂载
  tmp/                           # 日志、临时音频等运行时产物
  config/
    settings.py                  # 配置文件存在性检查
    config_loader.py             # 读取并合并配置，或从 manager-api 拉配置
    logger.py                    # loguru 日志配置
    manage_api_client.py         # manager-api 客户端
    assets/                      # 提示音、绑定码音频等静态音频资源
  core/
    websocket_server.py          # WebSocket 服务封装，认证、连接分发、热更新配置
    connection.py                # 单设备连接会话核心类，承载对话状态和处理链路
    http_server.py               # aiohttp HTTP 服务，挂载 OTA 和视觉分析路由
    api/
      ota_handler.py             # OTA GET/POST、WebSocket/MQTT 配置下发、固件下载
      vision_handler.py          # /mcp/vision/explain 视觉分析接口
    handle/
      textHandle.py              # 文本消息处理入口
      receiveAudioHandle.py      # 音频流/VAD/ASR 后进入聊天流程
      sendAudioHandle.py         # TTS 音频与状态消息下发
      intentHandler.py           # 退出、唤醒词、Intent、工具调用前置处理
      helloHandle.py             # hello 握手、MCP 初始化、唤醒词回复
      textHandler/               # hello/listen/abort/iot/mcp/ping/server 消息处理器
    providers/
      asr/                       # ASR Provider 实现
      tts/                       # TTS Provider 实现
      llm/                       # LLM Provider 实现
      vad/                       # VAD Provider 实现
      intent/                    # Intent Provider 实现
      memory/                    # Memory Provider 实现
      vllm/                      # 视觉大模型 Provider 实现
      tools/                     # 统一工具系统：插件、IoT、MCP、接入点
    utils/
      modules_initialize.py      # 根据 selected_module 动态初始化模块
      asr.py/tts.py/llm.py/...   # 各类 Provider 动态导入工厂
      dialogue.py                # 对话历史管理
      prompt_manager.py          # 系统提示词增强和上下文注入
      auth.py                    # Token 生成与校验
      audioRateController.py     # TTS 音频下发流控
  plugins_func/
    register.py                  # 插件注册装饰器、Action/ToolType/响应模型
    loadplugins.py               # 自动扫描导入插件模块
    functions/                   # 天气、新闻、播放音乐、Home Assistant、RAGFlow 等插件
  models/
    SenseVoiceSmall/             # 默认本地 ASR 模型相关文件
    snakers4_silero-vad/         # Silero VAD 相关模型代码
  performance_tester/            # ASR/LLM/VLLM/TTS 性能测试脚本
  test/
    test_page.html               # 浏览器音频交互测试页
    js/                          # 测试页 WebSocket、OTA、Opus、Live2D 等逻辑
```

## 启动入口

入口文件是 `app.py`。

启动流程大致如下：

1. `check_ffmpeg_installed()` 检查 FFmpeg 是否可用。
2. `load_config()` 加载配置。
3. 生成或读取 `server.auth_key`，用于 OTA Token、WebSocket 认证和视觉接口认证。
4. 启动全局 GC 管理器。
5. 创建并启动 `WebSocketServer`，默认监听 `server.ip:server.port`，也就是 `0.0.0.0:8000`。
6. 创建并启动 `SimpleHttpServer`，默认监听 `server.ip:server.http_port`，也就是 `0.0.0.0:8003`。
7. 输出 OTA、视觉分析、WebSocket 地址。
8. 等待退出信号，退出时取消任务、停止 GC、关闭连接。

源码运行：

```bash
python app.py
```

Docker 只运行 server：

```bash
docker compose up -d
docker logs -f xiaozhi-esp32-server
```

`docker-compose.yml` 只暴露两个端口：

- `8000`: WebSocket 服务，设备语音交互主链路。
- `8003`: HTTP 服务，简单 OTA 和视觉分析接口。

## 配置加载机制

默认配置在 `config.yaml`，用户自定义配置在 `data/.config.yaml`。

`config/config_loader.py` 的逻辑是：

1. 读取 `config.yaml` 作为默认配置。
2. 读取 `data/.config.yaml` 作为用户配置。
3. 如果 `data/.config.yaml` 中配置了 `manager-api.url`，则通过 `manager-api` 拉取配置。
4. 否则递归合并默认配置和用户配置，用户配置优先级更高。
5. 创建日志、模型输出等必要目录。
6. 将配置缓存到内存中，避免重复解析。

建议只在 `data/.config.yaml` 中写差异配置，例如：

```yaml
server:
  websocket: ws://127.0.0.1:8000/xiaozhi/v1/
  vision_explain: http://127.0.0.1:8003/mcp/vision/explain

selected_module:
  ASR: FunASR
  VAD: SileroVAD
  LLM: ChatGLMLLM
  TTS: EdgeTTS
  Intent: function_call
  Memory: mem_local_short
```

注意：如果启用了智控台，即 `manager-api.url` 有值，本地很多业务配置不会生效，应该去智控台配置。

## 配置关键项

### server

```yaml
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  websocket: ws://你的IP或域名:8000/xiaozhi/v1/
  vision_explain: http://你的IP或域名:8003/mcp/vision/explain
  auth:
    enabled: false
    allowed_devices:
      - "11:22:33:44:55:66"
  mqtt_gateway: null
  mqtt_signature_key: null
  udp_gateway: null
```

- `port`: WebSocket 监听端口。
- `http_port`: OTA 和视觉分析 HTTP 服务端口。
- `websocket`: OTA 接口返回给设备的 WebSocket 地址。Docker、公网、反代场景建议显式配置。
- `vision_explain`: 设备拍照/视觉分析时访问的 HTTP 地址，也会用于构造 OTA 固件下载地址。
- `auth.enabled`: 是否开启 WebSocket Token 校验。
- `mqtt_gateway`: 不为空时，OTA 会下发 MQTT 配置而不是 WebSocket 配置。

### selected_module

`selected_module` 决定运行时选用哪个 Provider。

```yaml
selected_module:
  VAD: SileroVAD
  ASR: FunASR
  LLM: ChatGLMLLM
  TTS: EdgeTTS
  Intent: function_call
  Memory: mem_local_short
```

每个选中的名字必须能在对应配置段里找到，例如：

- `ASR.FunASR.type: fun_local`
- `LLM.ChatGLMLLM.type: openai`
- `TTS.EdgeTTS.type: edge`
- `VAD.SileroVAD.type: silero`

Provider 工厂会根据 `type` 动态导入对应实现。

## WebSocket 服务

核心文件：

- `core/websocket_server.py`
- `core/connection.py`

`WebSocketServer` 启动时会先初始化公共模块：

- VAD
- ASR
- LLM
- Intent
- Memory

然后通过 `websockets.serve()` 监听设备连接。

连接处理逻辑：

1. `_handle_connection()` 读取请求头。
2. 如果没有 `device-id`，尝试从 URL query 中读取。
3. 如果启用认证，调用 `_handle_auth()` 校验 `Authorization: Bearer <token>`。
4. 为每个设备连接创建一个独立的 `ConnectionHandler`。
5. 调用 `ConnectionHandler.handle_connection()` 进入设备会话。

`ConnectionHandler` 负责保存每个连接的状态：

- `session_id`
- `device_id`
- `client_ip`
- `audio_format`
- `sample_rate`
- `client_is_speaking`
- `client_listen_mode`
- `vad/asr/tts/llm/memory/intent`
- `dialogue`
- `iot_descriptors`
- `func_handler`
- ASR/TTS 队列
- 打断、超时、绑定、上报等状态

## HTTP/OTA 服务

核心文件：

- `core/http_server.py`
- `core/api/ota_handler.py`
- `core/api/vision_handler.py`

`SimpleHttpServer` 使用 `aiohttp` 启动 HTTP 服务。

只运行 Python server 时，会注册：

```text
GET     /xiaozhi/ota/
POST    /xiaozhi/ota/
GET     /xiaozhi/ota/download/{filename}
POST    /mcp/vision/explain
GET     /mcp/vision/explain
```

### OTA GET

用于人工检查 OTA 是否正常：

```text
http://你的IP:8003/xiaozhi/ota/
```

正常返回：

```text
OTA接口运行正常，向设备发送的websocket地址是：ws://你的IP:8000/xiaozhi/v1/
```

### OTA POST

设备启动后会请求 OTA 接口。服务端返回：

- `server_time`: 服务器时间和时区。
- `firmware`: 固件版本和升级地址。
- `websocket`: WebSocket URL 和 Token。
- 或 `mqtt`: MQTT 网关连接配置。

如果 `server.mqtt_gateway` 为空，返回 WebSocket：

```json
{
  "websocket": {
    "url": "ws://127.0.0.1:8000/xiaozhi/v1/",
    "token": ""
  }
}
```

如果 `server.mqtt_gateway` 不为空，返回 MQTT 配置。

### 固件下载

`/xiaozhi/ota/download/{filename}` 只允许下载 `data/bin` 目录下的 `.bin` 文件。`ota_handler.py` 会根据设备型号和版本查找候选固件。

### 视觉分析

`/mcp/vision/explain` 接收 `multipart/form-data`：

- `question`: 问题文本。
- 图片文件字段。

接口会校验 Token，读取 VLLM 配置，创建视觉模型 Provider，将图片转成 base64 后调用模型。

## 设备消息类型

文本消息入口是 `core/handle/textHandle.py`，实际处理由 `TextMessageProcessor` 和 `TextMessageHandlerRegistry` 分发。

支持的消息类型定义在 `core/handle/textMessageType.py`：

```text
hello
abort
listen
iot
mcp
server
ping
```

### hello

处理文件：

- `core/handle/textHandler/helloMessageHandler.py`
- `core/handle/helloHandle.py`

作用：

- 读取客户端音频参数，例如 `format`、`sample_rate`、`channels`、`frame_duration`。
- 更新连接中的 `audio_format`。
- 记录设备支持的能力，例如 MCP。
- 如果设备支持 MCP，则创建设备 MCP Client 并发送初始化消息。
- 返回服务端 hello 消息，即 `config.xiaozhi` 加上当前 `session_id`。

### listen

处理文件：

- `core/handle/textHandler/listenMessageHandler.py`

常见状态：

- `start`: 设备开始监听，服务端清空音频状态。
- `stop`: 设备停止监听，非流式 ASR 会触发识别。
- `detect`: 设备侧检测到文字，可直接进入 `startToChat()`，常用于唤醒词或前端测试。

### abort

处理文件：

- `core/handle/textHandler/abortMessageHandler.py`
- `core/handle/abortHandle.py`

用于用户打断当前播报，服务端会设置 `client_abort`，清理 TTS/音频状态。

### iot

处理文件：

- `core/handle/textHandler/iotMessageHandler.py`
- `core/providers/tools/device_iot/*`

设备上报 IoT 能力描述和状态：

- `descriptors`: 注册设备可控属性/方法，转成可供 LLM function calling 使用的工具。
- `states`: 更新设备状态。

### mcp

处理文件：

- `core/handle/textHandler/mcpMessageHandler.py`
- `core/providers/tools/device_mcp/*`

用于设备 MCP 通信。设备 hello 中声明 `features.mcp` 后，服务端会初始化 MCP Client。

## 音频输入到回复播放的主链路

完整链路如下：

```text
ESP32 麦克风
  -> WebSocket binary 音频包
  -> ConnectionHandler._route_message()
  -> asr_audio_queue
  -> ASRProviderBase.asr_text_priority_thread()
  -> receiveAudioHandle.handleAudioMessage()
  -> VAD 判断是否有人声
  -> ASRProviderBase.receive_audio()
  -> 语音停止时 ASRProviderBase.handle_voice_stop()
  -> speech_to_text_wrapper()
  -> receiveAudioHandle.startToChat()
  -> intentHandler.handle_user_intent()
  -> ConnectionHandler.chat()
  -> LLM streaming response
  -> TTSProviderBase.tts_text_queue
  -> TTSProviderBase.tts_text_priority_thread()
  -> text_to_speak()
  -> Opus 编码
  -> TTSProviderBase.tts_audio_queue
  -> sendAudioHandle.sendAudioMessage()
  -> WebSocket binary 音频包
  -> ESP32 扬声器播放
```

### 音频接收

设备发送的二进制消息会进入 `ConnectionHandler._route_message()`。

普通 WebSocket 连接下，音频直接放入：

```text
conn.asr_audio_queue
```

如果连接来自 MQTT 网关，会先解析 16 字节音频头，按时间戳做乱序缓冲，再放入 ASR 队列。

### VAD

`receiveAudioHandle.handleAudioMessage()` 调用：

```python
conn.vad.is_vad(conn, audio)
```

判断当前音频帧是否有人声。VAD 还参与空闲超时检测，如果长时间没有语音，会触发结束对话提示或关闭连接。

### ASR

ASR 基类是 `core/providers/asr/base.py` 的 `ASRProviderBase`。

关键点：

- `open_audio_channels()` 会启动 `asr_text_priority_thread`。
- 该线程不断从 `conn.asr_audio_queue` 取音频。
- 自动模式下，VAD 检测到语音停止后触发 `handle_voice_stop()`。
- 手动模式下，设备发送 `listen.stop` 后触发识别。
- `handle_voice_stop()` 会调用具体 Provider 的 `speech_to_text_wrapper()`。
- 如果启用声纹识别，会同时进行声纹识别，并把说话人信息写入识别结果。

ASR 结果可能是纯文本，也可能是包含语言、情绪、说话人等字段的 JSON 字符串。最终都会进入 `startToChat()`。

### Intent 和唤醒词

`startToChat()` 会先走 `handle_user_intent()`。

处理顺序：

1. 解析 ASR 返回的 JSON，提取 `content` 和 `speaker`。
2. 检查退出命令，例如 `退出`、`关闭`。
3. 检查是否是唤醒词。
4. 如果 `Intent` 是 `function_call`，不单独分析意图，直接进入 LLM function calling。
5. 如果 `Intent` 是 `intent_llm`，先用意图模型判断是否需要工具调用。
6. 未被意图处理时，进入普通聊天。

### LLM

核心方法是 `ConnectionHandler.chat()`。

它负责：

- 创建 `sentence_id`。
- 将用户消息写入 `Dialogue`。
- 查询 Memory，并将记忆注入 LLM 对话。
- 如果开启 `function_call`，从 `UnifiedToolHandler` 获取工具函数描述。
- 调用 `llm.response()` 或 `llm.response_with_functions()`。
- 持续读取流式返回内容。
- 将普通文本片段放入 `tts.tts_text_queue`。
- 收集工具调用请求并执行。
- 把最终 assistant 回复写回对话历史。
- 发送 `SentenceType.LAST` 通知 TTS 完成。

### TTS

TTS 基类是 `core/providers/tts/base.py` 的 `TTSProviderBase`。

每个连接初始化 TTS 后，会启动两个线程：

- `tts_text_priority_thread`: 消费 `tts_text_queue`，根据标点切分句子，调用 `text_to_speak()` 合成音频。
- `_audio_play_priority_thread`: 消费 `tts_audio_queue`，调用 `sendAudioMessage()` 下发音频。

TTS 文本消息分三种：

- `FIRST`: 一轮回复开始。
- `MIDDLE`: 中间文本片段。
- `LAST`: 一轮回复结束。

`sendAudioHandle.py` 会负责：

- 向设备发送 `tts` 状态消息，例如 `sentence_start`、`stop`。
- 将 Opus 音频包通过 WebSocket 发送给设备。
- 使用 `AudioRateController` 控制音频包发送节奏，避免一次性推太快。
- 处理 MQTT 网关场景下的 16 字节音频头。

## Provider 机制

项目用 Provider 模式适配不同供应商。

动态初始化入口：

- `core/utils/modules_initialize.py`

动态导入工厂：

- `core/utils/asr.py`
- `core/utils/tts.py`
- `core/utils/llm.py`
- `core/utils/vad.py`
- `core/utils/intent.py`
- `core/utils/memory.py`
- `core/utils/vllm.py`

规则是：

1. 从 `selected_module` 找到当前模块名。
2. 在对应配置段找到该模块配置。
3. 读取配置中的 `type`。
4. 根据 `type` 动态 import 对应 Provider。
5. 实例化统一命名的 Provider 类。

例如 ASR：

```yaml
selected_module:
  ASR: FunASR

ASR:
  FunASR:
    type: fun_local
```

会加载：

```text
core/providers/asr/fun_local.py
```

并实例化其中的：

```python
ASRProvider(...)
```

LLM 稍有不同，目录结构是：

```text
core/providers/llm/openai/openai.py
```

并实例化：

```python
LLMProvider(...)
```

TTS 会加载：

```text
core/providers/tts/{type}.py
```

并实例化：

```python
TTSProvider(...)
```

## 已支持的模块类型

### ASR

目录：`core/providers/asr/`

示例 Provider：

- `fun_local`: 本地 FunASR。
- `fun_server`: FunASR 服务端。
- `sherpa_onnx_local`: 本地 Sherpa ONNX。
- `aliyun`、`aliyun_stream`、`aliyunbl_stream`
- `doubao`、`doubao_stream`
- `xunfei_stream`
- `tencent`
- `baidu`
- `openai`
- `qwen3_asr_flash`
- `vosk`

### VAD

目录：`core/providers/vad/`

默认是：

- `silero`

### LLM

目录：`core/providers/llm/`

示例 Provider：

- `openai`: 兼容 OpenAI 接口，常用于阿里百炼、火山、DeepSeek、智谱等。
- `ollama`
- `dify`
- `fastgpt`
- `coze`
- `gemini`
- `xinference`
- `homeassistant`
- `AliBL`

### TTS

目录：`core/providers/tts/`

示例 Provider：

- `edge`
- `doubao`
- `aliyun`、`aliyun_stream`、`alibl_stream`
- `huoshan_double_stream`
- `xunfei_stream`
- `tencent`
- `openai`
- `minimax_httpstream`
- `gpt_sovits_v2`、`gpt_sovits_v3`
- `fishspeech`
- `index_stream`
- `paddle_speech`
- `siliconflow`
- `cozecn`
- `custom`

### Intent

目录：`core/providers/intent/`

- `nointent`: 不做意图识别。
- `intent_llm`: 先让意图模型判断是否调用工具。
- `function_call`: 直接让主 LLM 通过 function calling 决定工具调用。

### Memory

目录：`core/providers/memory/`

- `nomem`: 无记忆。
- `mem_local_short`: 本地短期记忆。
- `mem0ai`: mem0ai 接口。
- `powermem`: PowerMem。
- `mem_report_only`: 仅上报模式。

### VLLM

目录：`core/providers/vllm/`

用于视觉分析接口，目前主要走兼容 OpenAI 风格的 Provider。

## 工具与插件系统

工具系统分两层：

1. 老的插件注册机制：`plugins_func/`
2. 新的统一工具管理机制：`core/providers/tools/`

### 插件注册

`plugins_func/loadplugins.py` 会自动导入 `plugins_func.functions` 下所有模块。

插件通过 `register_function()` 注册，例如：

```python
@register_function("get_weather", desc, ToolType.WAIT)
def get_weather(...):
    ...
```

注册结果存在 `all_function_registry`，后续由工具执行器读取。

插件返回 `ActionResponse`：

- `Action.RESPONSE`: 工具结果直接回复用户。
- `Action.REQLLM`: 工具结果再次交给 LLM 总结。
- `Action.NONE`: 不额外处理。
- `Action.NOTFOUND`: 工具不存在。
- `Action.ERROR`: 工具执行错误。

### 统一工具处理器

核心文件：

- `core/providers/tools/unified_tool_handler.py`
- `core/providers/tools/unified_tool_manager.py`

`UnifiedToolHandler` 会注册多个执行器：

- `ServerPluginExecutor`: 服务端 Python 插件。
- `ServerMCPExecutor`: 服务端 MCP。
- `DeviceIoTExecutor`: 设备 IoT。
- `DeviceMCPExecutor`: 设备 MCP。
- `MCPEndpointExecutor`: MCP 接入点。

LLM function calling 时：

1. `ConnectionHandler.chat()` 从 `func_handler.get_functions()` 获取工具描述。
2. LLM 返回工具调用。
3. `UnifiedToolHandler.handle_llm_function_call()` 解析函数名和参数。
4. `ToolManager.execute_tool()` 找到工具类型和对应执行器。
5. 执行器返回 `ActionResponse`。
6. `ConnectionHandler._handle_function_result()` 决定直接播报，还是把工具结果再交给 LLM。

## 会话生命周期

单个设备连接的大致生命周期：

```text
WebSocket 握手
  -> 鉴权
  -> 创建 ConnectionHandler
  -> 后台初始化私有配置和组件
  -> 接收 hello
  -> 返回服务端 hello
  -> 接收 listen/audio/iot/mcp/abort 等消息
  -> 用户语音触发聊天
  -> LLM/TTS 回复
  -> 空闲超时或设备断开
  -> 保存记忆
  -> 清理 TTS/ASR/工具/MCP/线程/队列
```

`ConnectionHandler` 的后台初始化包括：

- 如果启用 `manager-api`，按 `device-id` 和 `client-id` 拉设备私有配置。
- 初始化 TTS。
- 初始化 ASR。
- 初始化声纹识别。
- 初始化 Memory。
- 初始化 Intent。
- 初始化工具处理器。
- 增强系统提示词。
- 启动上报线程。

## 线程与队列模型

虽然服务主体是 `asyncio`，但音频和模型处理也大量使用线程与队列。

主要队列：

- `conn.asr_audio_queue`: WebSocket 收到的音频帧。
- `conn.asr_audio`: 当前语音片段缓存。
- `tts.tts_text_queue`: LLM 流式输出文本片段。
- `tts.tts_audio_queue`: TTS 生成后的 Opus 音频包。
- `conn.report_queue`: ASR/TTS/工具调用上报。

主要线程：

- ASR 音频消费线程。
- TTS 文本消费线程。
- TTS 音频播放线程。
- 上报线程。
- 记忆保存守护线程。

设计上，WebSocket 事件循环只做快速分发，耗时工作尽量放到线程或 Provider 内部异步任务中。

## 设备接入流程

对于官方较新的固件，设备通常先访问 OTA，再根据 OTA 返回结果连接 WebSocket。

建议流程：

1. 部署 `xiaozhi-server`。
2. 在 `data/.config.yaml` 中配置：

```yaml
server:
  websocket: ws://你的IP:8000/xiaozhi/v1/
  vision_explain: http://你的IP:8003/mcp/vision/explain
```

3. 浏览器访问：

```text
http://你的IP:8003/xiaozhi/ota/
```

4. 确认返回的 WebSocket 地址正确。
5. 在小智设备配网页面的高级选项中填写 OTA 地址：

```text
http://你的IP:8003/xiaozhi/ota/
```

6. 重启设备，观察服务端日志是否出现 OTA 请求和 WebSocket 连接。

## 最小部署关注点

如果只想跑语音助手闭环，重点关注：

- `app.py`
- `docker-compose.yml`
- `data/.config.yaml`
- `config.yaml`
- `core/websocket_server.py`
- `core/connection.py`
- `core/handle/receiveAudioHandle.py`
- `core/handle/sendAudioHandle.py`
- `core/providers/asr/`
- `core/providers/llm/`
- `core/providers/tts/`
- `core/providers/vad/`
- `plugins_func/functions/`

可以暂时忽略：

- `config_from_api.yaml`
- `config/manage_api_client.py`
- 设备绑定逻辑
- 聊天记录上报
- 智控台私有配置拉取
- 多用户/权限/后台管理相关能力

## 二次开发建议

### 新增 ASR/TTS/LLM Provider

按现有 Provider 结构新增文件，并保证类名符合约定：

- ASR: `core/providers/asr/{type}.py`，类名 `ASRProvider`
- TTS: `core/providers/tts/{type}.py`，类名 `TTSProvider`
- LLM: `core/providers/llm/{type}/{type}.py`，类名 `LLMProvider`

然后在 `config.yaml` 或 `data/.config.yaml` 中增加配置，并把 `selected_module` 指向该配置。

### 新增插件工具

在 `plugins_func/functions/` 下新增 Python 文件。

使用 `register_function()` 注册函数描述和函数体，然后在 `Intent.function_call.functions` 或对应配置中启用。

工具描述需要尽量清晰，因为 LLM 会根据描述决定是否调用工具。

### 改造主对话流程

主流程集中在：

- `receiveAudioHandle.startToChat()`
- `intentHandler.handle_user_intent()`
- `ConnectionHandler.chat()`

如果只是换模型或换 TTS，不建议改这里。
如果要改变“先意图再聊天”“工具调用结果是否再交给 LLM”“回复分段策略”等行为，再考虑修改这些文件。

### 改造音频下发策略

关注：

- `core/handle/sendAudioHandle.py`
- `core/utils/audioRateController.py`
- `core/providers/tts/base.py`

这里决定 Opus 包下发节奏、预缓冲包数量、打断后是否丢弃旧音频等。

## 常见排查

### OTA 能访问，但设备连不上 WebSocket

检查：

- `server.websocket` 是否是设备能访问的地址。
- Docker 场景不要写容器内地址。
- 公网部署时协议是否应为 `wss://`，反代路径是否保留 `/xiaozhi/v1/`。
- 防火墙是否放行 8000 或反代端口。

### 设备连上但没声音

检查：

- TTS Provider 是否初始化成功。
- `server.websocket` 返回地址是否正确。
- 设备 hello 中的 `audio_params` 和服务端采样率是否匹配。
- 日志里是否有 TTS 超时或音频文件不存在。

### 识别不到语音

检查：

- 是否下载并挂载了 `models/SenseVoiceSmall/model.pt`。
- `selected_module.ASR` 和 `ASR.*.type` 是否匹配。
- FFmpeg、libopus 是否安装。
- VAD 参数是否过于严格，例如 `min_silence_duration_ms`。

### 工具调用不生效

检查：

- `selected_module.Intent` 是否是 `function_call` 或 `intent_llm`。
- 插件是否在 `plugins_func/functions/` 中被自动导入。
- 配置中的 `functions` 是否包含目标插件。
- 日志里 `当前支持的函数列表` 是否包含目标函数。

### 想跳过后台管理

确保 `data/.config.yaml` 没有配置 `manager-api.url`。
只使用本地配置时，服务会走简单 OTA 接口，并直接从本地配置初始化各 Provider。
