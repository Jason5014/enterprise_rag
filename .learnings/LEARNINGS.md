
## [LRN-20260521-001] Text Splitter 无限循环 (dead_loop)

**Logged**: 2026-05-21T17:00:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
当剩余文本 < chunk_overlap * 2 时，start位置不前进导致死循环

### Details
在 _create_parent_chunks 和 _create_child_chunks 中，每个chunk处理完后计算 `start = end - chunk_overlap`。
当剩余文本不足时，end 位置不变，start 也就无法前进，导致无限循环。

### Suggested Action
在循环中添加：
```python
if len(text) - start < self.chunk_overlap * 2:
    start = len(text)  # 剩余太少，直接结束
```

### Metadata
- Source: error
- Related Files: src/text_splitter.py (_create_parent_chunks, _create_child_chunks)
- Pattern-Key: text_splitter.dead_loop
- Recurrence-Count: 1
- First-Seen: 2026-05-21

---
## [LRN-20260521-002] ParentChunk parent_id bug

**Logged**: 2026-05-21T17:00:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
ParentChunk.__init__ 中 parent_id=None 导致父子关联失效

### Details
ParentChunk.__init__ 实现为：
```python
super().__init__(..., parent_id=None)
```
应该是 `parent_id=parent_id`（自己的 chunk_id 就是自己的 parent_id）

### Suggested Action
修复为 `parent_id=parent_id`

### Metadata
- Source: error
- Related Files: src/text_splitter.py (ParentChunk class)
- Pattern-Key: text_splitter.parent_id
- Recurrence-Count: 1
- First-Seen: 2026-05-21

---
## [LRN-20260521-003] DashScope text-embedding-v3 batch限制

**Logged**: 2026-05-21T17:00:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
DashScope text-embedding-v3 API 单次最多10条，不是文档说的25条

### Details
调用 batch embedding 时，API 限制单次最多10条。代码中 batch_size 可能设置大于10。

### Suggested Action
在代码中强制 `batch_size = min(self.config.batch_size, 10)`

### Metadata
- Source: error
- Related Files: src/embedding.py
- Pattern-Key: dashscope.batch_limit
- Recurrence-Count: 1
- First-Seen: 2026-05-21

---
## [LRN-20260523-001] DashScope API导入错误

**Logged**: 2026-05-23T10:00:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
`from dashscope import DashScope` 导入失败，正确方式是 `from dashscope import Generation`

### Details
代码中使用了错误的导入 `from dashscope import DashScope`，导致 `DASHSCOPE_AVAILABLE=False`，所有LLM调用都失败。

实际验证：
- `dashscope` 模块中有 `Generation`、`TextEmbedding` 等类
- 没有 `DashScope` 类
- 调用应该用 `Generation.call()` 而不是 `DashScope.call()`

### Suggested Action
统一使用 `from dashscope import Generation` 并用 `Generation.call()` 调用

### Metadata
- Source: error
- Related Files: src/query_router.py, src/answer_generator.py
- Pattern-Key: dashscope.import_error
- Recurrence-Count: 1
- First-Seen: 2026-05-23

---
## [LRN-20260521-004] DashScope TextEmbedding.call 参数名

**Logged**: 2026-05-21T17:00:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
DashScope TextEmbedding.call 参数名是 input 不是 texts，响应状态字段是 status_code 不是 status

### Details
调用 DashScope TextEmbedding 时：
- 参数名应该是 `input` 不是 `texts`
- 响应状态字段是 `status_code` 不是 `status`

### Suggested Action
使用正确的参数名和字段名

### Metadata
- Source: error
- Related Files: src/embedding.py
- Pattern-Key: dashscope.api_params
- Recurrence-Count: 1
- First-Seen: 2026-05-21

---
