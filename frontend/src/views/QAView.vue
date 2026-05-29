<template>
  <div class="qa-layout">
    <!-- 顶部工具栏 -->
    <div class="qa-toolbar">
      <el-select v-model="activeKBId" placeholder="选择知识库（默认内置）" clearable
        style="width:200px;" @change="qaStore.clearHistory()">
        <el-option v-for="kb in kbList" :key="kb.kb_id" :label="kb.name" :value="kb.kb_id" />
      </el-select>

      <el-select v-model="configName" style="width:140px; margin-left:10px;" title="检索配置预设">
        <el-option label="BASE（基础）" value="base" />
        <el-option label="FAST（快速）" value="fast" />
        <el-option label="PRECISION（高精度）" value="precision" />
        <el-option label="FULL（完整）" value="full" />
      </el-select>

      <el-tag type="info" style="margin-left:10px; font-size:11px;" effect="plain">
        {{ configLabels[configName] }}
      </el-tag>

      <el-button text @click="clearHistory" :icon="Delete" style="margin-left:auto;">清空对话</el-button>
    </div>

    <!-- 消息区 -->
    <div class="messages" ref="messagesEl">
      <div v-if="messages.length === 0" class="empty-hint">
        <el-icon size="48" color="#c0c4cc"><ChatDotRound /></el-icon>
        <p>向知识库提问吧，当前配置：<strong>{{ configName.toUpperCase() }}</strong></p>
      </div>

      <div v-for="(msg, i) in messages" :key="i" :class="['message-row', msg.role]">
        <div class="avatar">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
        <div class="bubble">
          <!-- 加载中 -->
          <span v-if="msg.loading && !msg.content" class="typing-dot">●●●</span>
          <span v-else style="white-space:pre-wrap; word-break:break-word;">{{ msg.content }}</span>

          <!-- Auto Bad Case 警告 -->
          <div v-if="msg.role === 'assistant' && !msg.loading && msg.warnings?.length"
            style="margin-top:8px;">
            <el-alert v-for="w in msg.warnings" :key="w" :title="w" type="warning"
              show-icon :closable="false" style="margin-bottom:4px; font-size:12px;" />
          </div>

          <!-- 页码引用 -->
          <div v-if="msg.pages && msg.pages.length > 0"
            style="margin-top:8px; font-size:12px; color:#909399; display:flex; align-items:center; gap:4px;">
            <el-icon><Document /></el-icon>
            引用页码：{{ msg.pages.join(', ') }}
          </div>

          <!-- ===== 检索过程可视化 ===== -->
          <el-collapse v-if="msg.role === 'assistant' && !msg.loading && msg.retrievalProcess"
            style="margin-top:8px; border:none;">
            <el-collapse-item name="retrieval">
              <template #title>
                <span style="font-size:12px; color:#909399;">🔍 查看检索过程</span>
              </template>
              <div class="retrieval-panel">

                <!-- Stage 流程图 -->
                <div class="stage-flow">
                  <!-- Query Rewrite -->
                  <div class="stage-node" :class="msg.retrievalProcess.query_rewrite_enabled ? 'active' : 'disabled'">
                    <div class="stage-icon">✏️</div>
                    <div class="stage-label">Query 改写</div>
                    <div class="stage-status">{{ msg.retrievalProcess.query_rewrite_enabled ? '启用' : '关闭' }}</div>
                  </div>
                  <div class="stage-arrow">→</div>
                  <!-- MultiQuery -->
                  <div class="stage-node" :class="msg.retrievalProcess.multiquery_enabled ? 'active' : 'disabled'">
                    <div class="stage-icon">🔄</div>
                    <div class="stage-label">MultiQuery</div>
                    <div class="stage-status">
                      {{ msg.retrievalProcess.multiquery_enabled
                        ? `${msg.retrievalProcess.query_variants.length} 个变体`
                        : '关闭' }}
                    </div>
                  </div>
                  <div class="stage-arrow">→</div>
                  <!-- Retrieval -->
                  <div class="stage-node active">
                    <div class="stage-icon">🗃️</div>
                    <div class="stage-label">向量检索</div>
                    <div class="stage-status">{{ msg.retrievalProcess.pre_rerank_count }} 个候选</div>
                  </div>
                  <div class="stage-arrow">→</div>
                  <!-- Rerank -->
                  <div class="stage-node" :class="msg.retrievalProcess.rerank_applied ? 'active' : 'disabled'">
                    <div class="stage-icon">🗳️</div>
                    <div class="stage-label">Rerank 精排</div>
                    <div class="stage-status">
                      {{ msg.retrievalProcess.rerank_applied
                        ? `→ ${msg.retrievalProcess.post_rerank.length} 个`
                        : '关闭' }}
                    </div>
                  </div>
                </div>

                <!-- Query 改写详情 -->
                <template v-if="msg.retrievalProcess.query_rewrite_enabled && msg.retrievalProcess.rewritten_query">
                  <div class="detail-section">
                    <div class="detail-title">✏️ 改写结果</div>
                    <div class="detail-row">
                      <span class="detail-label">原始问题：</span>
                      <span class="detail-text original">{{ msg.retrievalProcess.original_query }}</span>
                    </div>
                    <div class="detail-row">
                      <span class="detail-label">改写后：</span>
                      <span class="detail-text rewritten">{{ msg.retrievalProcess.rewritten_query }}</span>
                    </div>
                  </div>
                </template>

                <!-- MultiQuery 变体 -->
                <template v-if="msg.retrievalProcess.multiquery_enabled && msg.retrievalProcess.query_variants.length > 1">
                  <div class="detail-section">
                    <div class="detail-title">🔄 MultiQuery 变体（{{ msg.retrievalProcess.query_variants.length }} 个）</div>
                    <div v-for="(v, vi) in msg.retrievalProcess.query_variants" :key="vi"
                      class="variant-item">
                      <span class="variant-idx">Q{{ vi + 1 }}</span>
                      <span class="variant-text">{{ v }}</span>
                    </div>
                  </div>
                </template>

                <!-- 检索结果对比（Rerank 前后） -->
                <div class="detail-section">
                  <el-tabs size="small" type="border-card" style="margin-top:4px;">
                    <el-tab-pane
                      :label="`Rerank 后（${msg.retrievalProcess.post_rerank.length}）`">
                      <ChunkTable :chunks="msg.retrievalProcess.post_rerank" highlight />
                    </el-tab-pane>
                    <el-tab-pane
                      :label="`Rerank 前（${msg.retrievalProcess.pre_rerank.length}）`">
                      <ChunkTable :chunks="msg.retrievalProcess.pre_rerank" />
                    </el-tab-pane>
                  </el-tabs>
                </div>

              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- 推理过程折叠 -->
          <el-collapse v-if="msg.role === 'assistant' && !msg.loading && msg.content"
            style="margin-top:4px; border:none;">
            <el-collapse-item name="a">
              <template #title>
                <span style="font-size:12px; color:#909399;">📖 查看推理过程</span>
              </template>
              <div style="font-size:12px; color:#606266; white-space:pre-wrap; line-height:1.6;">
                {{ msg.content }}
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- 反馈区 -->
          <div v-if="msg.role === 'assistant' && !msg.loading && msg.content"
            style="margin-top:10px;">
            <template v-if="msg.feedbackDone">
              <el-tag size="small" type="success" effect="plain">✅ 已收到反馈</el-tag>
            </template>
            <template v-else>
              <div style="display:flex; gap:6px; align-items:center;">
                <el-button size="small" @click="sendFeedback(msg, i, 'good')" :icon="CircleCheck">
                  有用
                </el-button>
                <el-button size="small" type="danger" plain @click="openBadForm(msg, i)" :icon="CircleClose">
                  有问题
                </el-button>
              </div>

              <!-- 差评详细表单 -->
              <el-card v-if="msg.showBadForm" shadow="never"
                style="margin-top:10px; background:#fff9f9; border-color:#fde2e2;">
                <div style="font-size:13px; font-weight:600; margin-bottom:10px; color:#f56c6c;">
                  请告诉我们问题所在
                </div>
                <el-form label-position="top" size="small">
                  <el-form-item label="错误类型">
                    <el-select v-model="msg.badForm!.error_type" placeholder="选择错误类型" style="width:100%;">
                      <el-option label="幻觉 - 编造了不存在的信息" value="hallucination" />
                      <el-option label="不相关 - 答非所问" value="irrelevant" />
                      <el-option label="不完整 - 遗漏关键信息" value="incomplete" />
                      <el-option label="事实错误 - 数据或事实有误" value="factual_error" />
                      <el-option label="过时 - 信息不是最新的" value="outdated" />
                      <el-option label="其他" value="other" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="正确答案（可选）">
                    <el-input v-model="msg.badForm!.correct_answer" type="textarea" :rows="2"
                      placeholder="请填写正确答案，帮助改进系统" />
                  </el-form-item>
                  <el-form-item label="补充说明（可选）">
                    <el-input v-model="msg.badForm!.comment" placeholder="其他补充说明" />
                  </el-form-item>
                  <div style="display:flex; gap:8px;">
                    <el-button size="small" type="primary" @click="submitBadFeedback(msg, i)">提交反馈</el-button>
                    <el-button size="small" @click="msg.showBadForm = false">取消</el-button>
                  </div>
                </el-form>
              </el-card>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入框 -->
    <div class="input-area">
      <el-input
        v-model="inputText"
        placeholder="输入问题，例如：中芯国际2024年营收是多少？"
        :disabled="streaming"
        @keydown.enter.exact.prevent="sendQuestion"
        style="flex:1;"
      >
        <template #suffix>
          <el-button type="primary" :icon="Promotion" :loading="streaming"
            @click="sendQuestion" circle />
        </template>
      </el-input>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch, defineComponent, h } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Promotion, ChatDotRound, Document, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { kbApi } from '@/api/kb'
import { qaApi } from '@/api/qa'
import { useQAStore, type Message, type ChunkSummary } from '@/stores/qa'
import { useConfigStore, CONFIG_LABELS } from '@/stores/config'

// ---- 内联子组件：Chunk 表格 ----
const ChunkTable = defineComponent({
  props: {
    chunks: { type: Array as () => ChunkSummary[], required: true },
    highlight: { type: Boolean, default: false },
  },
  setup(props) {
    return () => h('div', { style: 'overflow-x:auto;' }, [
      h('table', { style: 'width:100%; border-collapse:collapse; font-size:11px;' }, [
        h('thead', {}, [
          h('tr', { style: 'background:#f5f7fa; color:#606266;' }, [
            h('th', { style: 'padding:4px 8px; text-align:left; width:30px;' }, '#'),
            h('th', { style: 'padding:4px 8px; text-align:left;' }, 'Chunk ID'),
            h('th', { style: 'padding:4px 8px; text-align:right; width:60px;' }, '得分'),
            h('th', { style: 'padding:4px 8px; text-align:right; width:50px;' }, '页码'),
            h('th', { style: 'padding:4px 8px; text-align:left;' }, '摘要'),
          ]),
        ]),
        h('tbody', {}, props.chunks.map((c, idx) => {
          const rowStyle = props.highlight && idx === 0
            ? 'background:#f0f9eb;'
            : idx % 2 === 0 ? '' : 'background:#fafafa;'
          return h('tr', { key: c.chunk_id, style: rowStyle }, [
            h('td', { style: 'padding:4px 8px; color:#909399;' },
              idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : String(idx + 1)
            ),
            h('td', { style: 'padding:4px 8px; color:#409eff; font-family:monospace; white-space:nowrap; max-width:160px; overflow:hidden; text-overflow:ellipsis;' }, c.chunk_id),
            h('td', { style: `padding:4px 8px; text-align:right; font-weight:600; color:${c.score > 0.7 ? '#67c23a' : c.score > 0.4 ? '#e6a23c' : '#f56c6c'};` }, c.score.toFixed(3)),
            h('td', { style: 'padding:4px 8px; text-align:right; color:#909399;' }, c.page ?? '-'),
            h('td', { style: 'padding:4px 8px; color:#606266; max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;' }, c.snippet),
          ])
        })),
      ]),
    ])
  },
})

const qaStore = useQAStore()
const configStore = useConfigStore()
const messages = computed(() => qaStore.messages)
const activeKBId = ref<string | null>(null)
// 与全局 configStore 双向绑定
const configName = computed({
  get: () => configStore.activeConfigName,
  set: (v) => { configStore.activeConfigName = v },
})
const inputText = ref('')
const streaming = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const kbList = ref<any[]>([])
const configLabels = CONFIG_LABELS

// Bad Case 自动检测词
const FALLBACK_PHRASES = ['无法找到', '没有相关信息', '未找到', '无法回答', '没有找到', '无法从上下文中', '抱歉', '暂无']

function detectWarnings(content: string, pages: number[]): string[] {
  const warns: string[] = []
  for (const phrase of FALLBACK_PHRASES) {
    if (content.includes(phrase)) {
      warns.push(`答案包含兜底话术「${phrase}」，可能未检索到有效信息`)
      break
    }
  }
  if (!pages.length) warns.push('答案未引用任何页码，无法验证来源')
  if (content.length < 50) warns.push('答案过短，可能推理步骤不完整')
  return warns
}

onMounted(async () => {
  try { const res = await kbApi.list(); kbList.value = res.data } catch { /* ignore */ }
})

watch(messages, () => { nextTick(scrollBottom) }, { deep: true })

function scrollBottom() {
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

async function sendQuestion() {
  const q = inputText.value.trim()
  if (!q || streaming.value) return
  inputText.value = ''

  qaStore.addMessage({ role: 'user', content: q })
  qaStore.addMessage({ role: 'assistant', content: '', loading: true, pages: [], warnings: [] })

  streaming.value = true

  const token = localStorage.getItem('token') ?? ''
  const params = new URLSearchParams({ q, config_name: configName.value })
  if (activeKBId.value) params.append('kb_id', activeKBId.value)
  const ov = configStore.getOverridesJson()
  if (ov) params.append('overrides', ov)
  params.append('token', token)
  const es = new EventSource(`/api/qa/stream?${params.toString()}`)

  let fullText = ''
  let pages: number[] = []

  es.onmessage = (e) => {
    if (e.data === '[DONE]') {
      es.close()
      streaming.value = false
      const warnings = detectWarnings(fullText, pages)
      qaStore.updateLast({ loading: false, content: fullText || '（空响应）', pages, warnings })
      return
    }
    try {
      const parsed = JSON.parse(e.data)
      if (parsed.error) {
        es.close(); streaming.value = false
        qaStore.updateLast({ loading: false, content: `❌ ${parsed.error}` })
        return
      }
    } catch { /* 普通文本 token */ }
    fullText += e.data
    qaStore.updateLast({ content: fullText })
  }

  // 元数据事件（pages、retrieval_process）
  es.addEventListener('meta', (e: MessageEvent) => {
    try {
      const meta = JSON.parse(e.data)
      pages = meta.pages ?? []
      const patch: Partial<Message> = { pages }
      if (meta.retrieval_process) {
        patch.retrievalProcess = meta.retrieval_process
      }
      qaStore.updateLast(patch)
    } catch { /* ignore */ }
  })

  es.onerror = () => {
    es.close()
    streaming.value = false
    qaStore.updateLast({ loading: false, content: fullText || '连接错误，请重试' })
  }
}

async function clearHistory() {
  qaStore.clearHistory()
  try { await qaApi.clearHistory(activeKBId.value ?? undefined) } catch { /* ignore */ }
}

function getUserQuery(msg: Message): string {
  const idx = messages.value.indexOf(msg)
  const userMsg = messages.value.slice(0, idx).reverse().find(m => m.role === 'user')
  return userMsg?.content ?? ''
}

async function sendFeedback(msg: Message, idx: number, type: 'good' | 'bad') {
  const query = getUserQuery(msg)
  await qaApi.feedback({
    query,
    answer: msg.content,
    feedback: type,
    config_name: configName.value,
    pages: msg.pages ?? [],
  }).catch(() => {})
  qaStore.updateAt(idx, { feedbackDone: true })
  ElMessage.success(type === 'good' ? '感谢反馈！' : '已记录，我们会改进')
}

function openBadForm(msg: Message, idx: number) {
  qaStore.updateAt(idx, {
    showBadForm: true,
    badForm: { error_type: '', correct_answer: '', comment: '' }
  })
}

async function submitBadFeedback(msg: Message, idx: number) {
  const query = getUserQuery(msg)
  await qaApi.feedback({
    query,
    answer: msg.content,
    feedback: 'bad',
    config_name: configName.value,
    pages: msg.pages ?? [],
    error_type: msg.badForm?.error_type,
    correct_answer: msg.badForm?.correct_answer,
    comment: msg.badForm?.comment,
  }).catch(() => {})
  qaStore.updateAt(idx, { feedbackDone: true, showBadForm: false })
  ElMessage.success('感谢您的详细反馈，我们会持续改进！')
}
</script>

<style scoped>
.qa-layout {
  display: flex; flex-direction: column; height: 100%;
  background: #f5f7fa; overflow: hidden;
}
.qa-toolbar {
  padding: 10px 20px; background: #fff; border-bottom: 1px solid #ebeef5;
  display: flex; align-items: center; flex-shrink: 0;
}
.messages {
  flex: 1; overflow-y: auto; padding: 20px; display: flex;
  flex-direction: column; gap: 16px;
}
.empty-hint {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  justify-content: center; color: #c0c4cc; gap: 8px; padding: 60px 0;
}
.message-row {
  display: flex; gap: 10px; max-width: 900px;
}
.message-row.user { flex-direction: row-reverse; align-self: flex-end; }
.message-row.assistant { align-self: flex-start; }
.avatar {
  width: 36px; height: 36px; border-radius: 50%; background: #409eff;
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; flex-shrink: 0;
}
.message-row.user .avatar { background: #67c23a; }
.bubble {
  background: #fff; border-radius: 12px; padding: 12px 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06); max-width: 760px; line-height: 1.7;
}
.message-row.user .bubble { background: #ecf5ff; }
.typing-dot { animation: blink 1s infinite; color: #909399; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
.input-area {
  padding: 14px 20px; background: #fff; border-top: 1px solid #ebeef5;
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
}

/* 检索过程可视化 */
.retrieval-panel {
  font-size: 12px;
  padding: 8px 4px;
}

.stage-flow {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.stage-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  min-width: 80px;
  text-align: center;
}

.stage-node.active {
  background: #f0f9eb;
  border-color: #b3e19d;
}

.stage-node.disabled {
  background: #f5f7fa;
  border-color: #dcdfe6;
  opacity: 0.6;
}

.stage-icon { font-size: 16px; }
.stage-label { font-size: 11px; font-weight: 600; color: #303133; }
.stage-status { font-size: 10px; color: #909399; }

.stage-arrow {
  color: #c0c4cc;
  font-size: 16px;
  font-weight: 300;
  flex-shrink: 0;
}

.detail-section {
  margin-bottom: 10px;
  background: #fafafa;
  border-radius: 6px;
  padding: 8px 10px;
  border: 1px solid #ebeef5;
}

.detail-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
  font-size: 12px;
}

.detail-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 4px;
}

.detail-label {
  color: #909399;
  flex-shrink: 0;
  width: 70px;
}

.detail-text {
  line-height: 1.5;
}

.detail-text.original { color: #606266; }
.detail-text.rewritten { color: #409eff; font-weight: 500; }

.variant-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 4px;
}

.variant-idx {
  background: #409eff;
  color: #fff;
  border-radius: 10px;
  padding: 0 6px;
  font-size: 10px;
  flex-shrink: 0;
  line-height: 18px;
}

.variant-text { color: #606266; }
</style>
