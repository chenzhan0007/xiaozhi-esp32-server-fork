# 微信聊天记录导入与聊天风格化 V1 方案

本文记录第一期最终方案。目标是在不做模型微调的前提下，将微信聊天记录转成长期记忆和聊天风格配置，并接入当前 `xiaozhi-server + PowerMem` 体系。

## 目标

- 支持用户上传微信聊天记录。
- 从聊天记录中抽取长期记忆，写入 PowerMem。
- 从目标人物聊天样本中生成聊天风格画像。
- 运行时按 `device_id` 注入长期记忆和风格 prompt。
- 后台系统可查看、管理导入记录、记忆条目和风格配置。

## 第一期开关

第一期只支持：

- 导入格式：`WeChatMsg CSV`
- 备选格式：`PyWxDump`，暂不实现，只保留后续扩展位。
- 文本来源：微信文本消息。
- 图片/截图 OCR：暂不实现，放到后续版本。
- 风格控制：静态 `prompt_fragment` 注入，不做动态 Style Controller。
- 记忆向量库：`PowerMem + SQLite`。
- 业务存储：由外部后台服务负责，`xiaozhi-server` 不保存业务表。

## 责任边界

### 外部后台服务

负责：

- Web 上传入口。
- WeChatMsg CSV 解析。
- 消息清洗和标准化。
- 聊天记录分段。
- 调用 LLM 抽取长期记忆。
- 调用 LLM 生成风格画像。
- 保存导入批次、记忆条目、风格画像。
- 提供后台管理页面。

### xiaozhi-server

负责：

- 提供 PowerMem 写入接口。
- 提供 PowerMem 搜索接口。
- 运行时按 `device_id` 使用长期记忆。
- 运行时按 `device_id` 注入风格 prompt。
- 保持原有 WebSocket 语音聊天链路。

## 输入格式

第一期只实现一个导入适配器：

```text
wechatmsg_csv_v1
```

用户通过 WeChatMsg 导出 CSV 后，在 Web 后台上传。

上传时需要填写：

```text
device_id
source_type = wechatmsg_csv_v1
user_name
target_person_name
file
```

## 标准消息结构

所有导入格式必须先转换为统一 messages。

```json
{
  "message_id": "wx_000001",
  "device_id": "device_xxx",
  "conversation_id": "contact_or_group_id",
  "timestamp": "2025-01-18T21:35:22+08:00",
  "sender_name": "张三",
  "role": "user",
  "msg_type": "text",
  "content": "清洗后的文本",
  "raw_content": "原始文本",
  "source": "wechat",
  "export_tool": "WeChatMsg",
  "import_batch_id": "batch_xxx"
}
```

`role` 取值：

```text
user      用户自己
target    目标风格对象
other     群聊其他人
system    系统消息
```

## 清洗规则

导入前需要过滤或规范化：

- 撤回提示、系统通知。
- 空消息、纯空白、乱码。
- 无语义占位符，如 `[图片]`、`[视频]`、`[文件]`。
- 重复消息。
- 低价值单字消息，如单独的“嗯”“哦”“好”，可用于风格统计，但不直接进入记忆抽取。
- 链接保留标题和域名，删除追踪参数。
- 高敏感信息按需脱敏，如手机号、证件号、银行卡、精确住址、公司敏感信息。

## 分段策略

第一期使用滑动时间窗口。

配置：

```text
聊天日边界：凌晨 04:00
窗口长度：3 个聊天日
滑动步长：2 个聊天日
重叠长度：1 个聊天日
```

示例：

```text
chunk_1: 第 1 天 04:00 -> 第 4 天 04:00
chunk_2: 第 3 天 04:00 -> 第 6 天 04:00
chunk_3: 第 5 天 04:00 -> 第 8 天 04:00
```

额外限制：

- 每个 chunk 最多 300 条消息。
- 超过上限时按时间顺序拆成 subchunk。
- chunk 之间有重叠，因此后续必须做语义去重。

## 记忆抽取

记忆抽取使用 LLM。

推荐模型：

```text
qwen3.5-flash
```

输入：

```text
清洗后的 chunk messages
```

输出 JSON 数组：

```json
[
  {
    "memory_type": "preference",
    "content": "用户疲惫时更希望被简短陪伴，而不是立刻收到大量建议。",
    "confidence": 0.86,
    "evidence_message_ids": ["wx_001", "wx_018"],
    "subject": "user",
    "related_person": "target_person",
    "source": "wechat",
    "privacy_level": "private"
  }
]
```

支持的 `memory_type`：

```text
profile
preference
relationship
event
emotion_pattern
style
user_instruction
```

过滤规则：

- `confidence < 0.65` 不写入 PowerMem。
- 无 evidence 的记忆不写入 PowerMem。
- 明显一次性寒暄不写入 PowerMem。
- 隐私风险过高的内容进入待审核，不自动写入。

## 记忆去重与合并

由于 chunk 有重叠，必须做去重。

第一期规则：

- 同一 `device_id`
- 同一 `memory_type`
- 语义相似或内容高度重复
- 保留 confidence 更高、证据更多、时间范围更完整的一条

可以先用 LLM 判断重复关系，也可以用 embedding 相似度做候选召回。

## PowerMem 写入

外部后台服务完成记忆抽取后，调用 `xiaozhi-server` 写入 PowerMem。

计划接口：

```text
POST /api/memory/import-items
GET  /api/memory/search?device_id=xxx&q=xxx
```

`import-items` 输入：

```json
{
  "device_id": "device_xxx",
  "import_batch_id": "batch_xxx",
  "items": [
    {
      "content": "用户疲惫时更希望被简短陪伴，而不是立刻收到大量建议。",
      "memory_type": "preference",
      "confidence": 0.86,
      "source": "wechat",
      "evidence_message_ids": ["wx_001", "wx_018"]
    }
  ]
}
```

PowerMem `user_id` 使用：

```text
device_id
```

## 业务存储

第一期业务数据由外部后台服务保存。

建议表：

```text
memory_import_batches:
  id
  device_id
  source_type
  file_name
  status
  total_messages
  total_chunks
  total_memory_items
  created_at
  updated_at

memory_items:
  id
  device_id
  content
  memory_type
  confidence
  source
  evidence_message_ids
  import_batch_id
  powermem_memory_id
  status
  created_at
  updated_at
  deleted_at
```

`status` 取值：

```text
active
disabled
deleted
pending_review
```

后台全量列表查询业务库；运行时召回查询 PowerMem。

## 风格抽取

风格抽取与记忆抽取分开处理。

模块：

```text
MemoryExtractor
StyleExtractor
```

风格抽取只分析 `role=target` 的消息。

推荐模型：

```text
qwen3.5-flash
```

输出：

```json
{
  "profile_json": {
    "tone": ["自然", "熟人感", "轻微调侃"],
    "sentence_length": "short_to_medium",
    "question_frequency": 0.25,
    "humor": 0.35,
    "directness": 0.55,
    "comfort_style": "先接住情绪，少分析，不连续追问"
  },
  "prompt_fragment": "和用户说话时保持熟人感，句子偏短，语气自然，不要像客服。用户低落时先陪伴，不急于分析，不连续追问。可以轻微调侃，但不要过度热情。"
}
```

## 风格存储

风格配置由外部后台服务保存。

建议表：

```text
style_profiles:
  id
  device_id
  target_person_name
  profile_json
  prompt_fragment
  version
  status
  created_at
  updated_at
```

第一期只使用 `prompt_fragment` 注入运行时 prompt。
`profile_json` 用于后台展示和后续动态风格控制。

## 用户长期指令

用户后续提出的长期要求不要直接写入 `style_profile.prompt_fragment`。

示例：

```text
以后每次对话你都要先叫我的名字。
以后回答尽量短一点。
以后不要叫我宝宝。
```

这类内容应作为独立长期记忆保存：

```json
{
  "memory_type": "user_instruction",
  "content": "用户希望每次对话开头先称呼他的名字。",
  "priority": "high"
}
```

运行时需要同时注入：

```text
base prompt
+ style_profile.prompt_fragment
+ user_instruction memories
+ PowerMem 相关记忆
+ 当前会话上下文
```

## 运行时注入

`xiaozhi-server` 后续需要支持按 `device_id` 获取风格 prompt。

运行时 prompt 组成：

```text
系统基础 prompt
+ 设备级 style prompt_fragment
+ PowerMem 检索结果
+ 当前连接内上下文
+ 当前用户输入
```

第一期可以先通过配置或外部接口获取 `prompt_fragment`。
后续再做动态 Style Controller。

## 第一期开工范围

第一期实现：

- WeChatMsg CSV 上传和解析。
- 标准化 messages。
- 3 天窗口 + 1 天重叠分段。
- LLM 抽取 memory items。
- LLM 生成 style profile。
- 业务库存储 import batch、memory items、style profile。
- 调用 `xiaozhi-server` 写入 PowerMem。
- 运行时注入 style prompt。

第一期不做：

- 截图 OCR。
- 多导出格式兼容。
- LoRA / SFT 微调。
- 动态 Style Controller。
- 复杂场景识别。
- 自动持续更新 style profile。
- PowerMem 云端向量库迁移。
