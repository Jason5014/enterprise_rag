<template>
  <div class="chat-layout">

    <!-- ── 顶部栏 ── -->
    <div class="chat-topbar">
      <div class="topbar-left">
        <el-select v-model="activeKBId" placeholder="默认内置知识库" clearable size="small"
          style="width:180px;" @change="qaStore.clearHistory()">
          <el-option v-for="kb in kbList" :key="kb.kb_id" :label="kb.name" :value="kb.kb_id" />
        </el-select>
        <div class="config-badge">
          <span class="config-dot" />
          <span>{{ configName.toUpperCase() }}</span>
          <span v-if="hasOverrides" class="override-dot">⚡</span>
        </div>
      </div>
      <button class="clear-btn" @click="clearHistory">
        <span>🗑</span> 清空
      </button>
    </div>

    <!-- ── 消息区 ── -->
    <div class="messages" ref="messagesEl">

      <!-- 空状态 -->
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">💬</div>
        <h3>向知识库提问</h3>
        <p>基于企业文档的智能问答，支持多轮对话</p>
        <div class="suggestions">
          <button v-for="s in SUGGESTIONS" :key="s" class="sugg-chip" @click="fillSuggestion(s)">
            {{ s }}
          </button>
        </div>
      </div>

      <!-- 消息列表 -->
      <template v-for="(msg, i) in messages" :key="i">
        <!-- 用户消息 -->
        <div v-if="msg.role === 'user'" class="msg-row user">
          <div class="msg-bubble user-bubble">{{ msg.content }}</div>
          <div class="avatar user-av">{{ userInitial }}</div>
        </div>

        <!-- AI 消息 -->
        <div v-else class="msg-row ai">
          <div class="avatar ai-av">AI</div>
          <div class="msg-card">

            <!-- 加载动画 -->
            <div v-if="msg.loading && !msg.content" class="typing">
              <span /><span /><span />
            </div>

            <!-- 内容（Markdown） -->
            <div v-else class="prose"
              v-html="renderMarkdown(msg.content)"
            />
            <!-- 流式光标 -->
            <span v-if="msg.loading && msg.content" class="cursor">▌</span>

            <!-- 警告 -->
            <div v-if="!msg.loading && msg.warnings?.length" class="warnings">
              <div v-for="w in msg.warnings" :key="w" class="warn-item">
                <span>⚠️</span> {{ w }}
              </div>
            </div>

            <!-- 页码引用 -->
            <div v-if="msg.pages && msg.pages.length > 0" class="pages-ref">
              <span class="ref-icon">📄</span>
              <span>引用页码：{{ msg.pages.join('、') }}</span>
            </div>

            <!-- 检索过程（可折叠） -->
            <details v-if="!msg.loading && msg.retrievalProcess" class="retrieval-details">
              <summary class="retrieval-summary">🔍 检索过程</summary>
              <div class="retrieval-body">

                <!-- Stage 流程图 -->
                <div class="stage-row">
                  <div v-for="(st, si) in getStages(msg.retrievalProcess)" :key="si" class="stage-wrap">
                    <div class="stage-node" :class="st.active ? 'active' : 'inactive'">
                      <span class="stage-em">{{ st.icon }}</span>
                      <span class="stage-name">{{ st.name }}</span>
                      <span class="stage-info">{{ st.info }}</span>
                    </div>
                    <span v-if="si < getStages(msg.retrievalProcess).length - 1" class="stage-arrow">›</span>
                  </div>
                </div>

                <!-- 改写对比 -->
                <div v-if="msg.retrievalProcess.rewritten_query" class="rewrite-box">
                  <div class="rw-label">原始</div>
                  <div class="rw-text muted">{{ msg.retrievalProcess.original_query }}</div>
                  <div class="rw-arrow">→</div>
                  <div class="rw-label">改写</div>
                  <div class="rw-text accent">{{ msg.retrievalProcess.rewritten_query }}</div>
                </div>

                <!-- MultiQuery -->
                <div v-if="msg.retrievalProcess.query_variants.length > 1" class="variants-box">
                  <div class="box-title">🔄 MultiQuery 变体</div>
                  <div v-for="(v, vi) in msg.retrievalProcess.query_variants" :key="vi" class="variant-row">
                    <span class="v-idx">Q{{ vi + 1 }}</span>
                    <span class="v-text">{{ v }}</span>
                  </div>
                </div>

                <!-- Chunk 对比（Tabs） -->
                <div class="chunk-tabs">
                  <div class="tab-bar">
                    <button class="tab-btn" :class="{ active: chunkTab[i] !== 'pre' }"
                      @click="setTab(i, 'post')">
                      Rerank 后 ({{ msg.retrievalProcess.post_rerank.length }})
                    </button>
                    <button class="tab-btn" :class="{ active: chunkTab[i] === 'pre' }"
                      @click="setTab(i, 'pre')">
                      Rerank 前 ({{ msg.retrievalProcess.pre_rerank.length }})
                    </button>
                  </div>
                  <div class="chunk-list">
                    <div v-for="(c, ci) in (chunkTab[i] === 'pre' ? msg.retrievalProcess.pre_rerank : msg.retrievalProcess.post_rerank)"
                      :key="c.chunk_id" class="chunk-row" :class="{ top: ci === 0 }">
                      <span class="chunk-rank">{{ ci === 0 ? '🥇' : ci === 1 ? '🥈' : ci === 2 ? '🥉' : ci + 1 }}</span>
                      <div class="chunk-info">
                        <div class="chunk-id">{{ c.chunk_id }}</div>
                        <div class="chunk-snippet">{{ c.snippet }}</div>
                      </div>
                      <div class="chunk-meta">
                        <span class="chunk-score" :style="{ color: scoreColor(c.score) }">{{ c.score.toFixed(3) }}</span>
                        <span v-if="c.page" class="chunk-page">p.{{ c.page }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </details>

            <!-- 反馈 -->
            <div v-if="!msg.loading && msg.content" class="feedback-row">
              <template v-if="msg.feedbackDone">
                <span class="feedback-done">✓ 已收到反馈</span>
              </template>
              <template v-else>
                <button class="fb-btn good" @click="sendFeedback(msg, i, 'good')">👍 有用</button>
                <button class="fb-btn bad" @click="openBadForm(msg, i)">👎 有问题</button>
              </template>

              <!-- 差评表单 -->
              <div v-if="msg.showBadForm" class="bad-form">
                <div class="bad-form-title">请告知具体问题</div>
                <el-select v-model="msg.badForm!.error_type" placeholder="错误类型" size="small" style="width:100%; margin-bottom:8px;">
                  <el-option label="幻觉 — 编造了不存在的信息" value="hallucination" />
                  <el-option label="不相关 — 答非所问" value="irrelevant" />
                  <el-option label="不完整 — 遗漏关键信息" value="incomplete" />
                  <el-option label="事实错误 — 数据有误" value="factual_error" />
                  <el-option label="过时 — 信息不是最新" value="outdated" />
                  <el-option label="其他" value="other" />
                </el-select>
                <el-input v-model="msg.badForm!.correct_answer" type="textarea" :rows="2"
                  placeholder="正确答案（可选）" size="small" style="margin-bottom:8px;" />
                <el-input v-model="msg.badForm!.comment" placeholder="补充说明（可选）" size="small" style="margin-bottom:8px;" />
                <div style="display:flex; gap:6px;">
                  <el-button size="small" type="primary" @click="submitBadFeedback(msg, i)">提交</el-button>
                  <el-button size="small" @click="msg.showBadForm = false">取消</el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ── 输入区 ── -->
    <div class="input-wrap">
      <div class="input-box" :class="{ focused: inputFocused }">
        <el-input
          v-model="inputText"
          placeholder="提问关于企业文档的任何问题…"
          :disabled="streaming"
          @keydown.enter.exact.prevent="sendQuestion"
          @focus="inputFocused = true"
          @blur="inputFocused = false"
          class="chat-input"
        />
        <button class="send-btn" :class="{ active: inputText.trim() }" :disabled="streaming || !inputText.trim()"
          @click="sendQuestion">
          <span v-if="streaming" class="send-loading">⏳</span>
          <span v-else>↑</span>
        </button>
      </div>
      <div class="input-hint">Enter 发送 · Shift+Enter 换行</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { kbApi } from '@/api/kb'
import { qaApi } from '@/api/qa'
import { useQAStore, type Message, type RetrievalProcess } from '@/stores/qa'
import { useConfigStore } from '@/stores/config'
import { renderMarkdown } from '@/utils/markdown'
import { useAuthStore } from '@/stores/auth'

const qaStore = useQAStore()
const configStore = useConfigStore()
const authStore = useAuthStore()
const messages = computed(() => qaStore.messages)
const activeKBId = ref<string | null>(null)
const configName = computed({
  get: () => configStore.activeConfigName,
  set: (v) => { configStore.activeConfigName = v },
})
const hasOverrides = computed(() => configStore.hasOverrides)
const inputText = ref('')
const inputFocused = ref(false)
const streaming = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const kbList = ref<any[]>([])
const chunkTab = ref<Record<number, 'pre' | 'post'>>({})

const userInitial = computed(() => ((authStore.user?.username ?? 'U')[0] ?? 'U').toUpperCase())

const SUGGESTIONS = [
  '中芯国际 2024 年营收是多少？',
  '公司近三年的研发投入趋势如何？',
  '主要竞争对手和市场份额占比？',
  '最新财报的核心风险因素？',
]

const FALLBACK_PHRASES = ['无法找到', '没有相关信息', '未找到', '无法回答', '没有找到', '无法从上下文中', '抱歉', '暂无']

function detectWarnings(content: string, pages: number[]): string[] {
  const warns: string[] = []
  for (const phrase of FALLBACK_PHRASES) {
    if (content.includes(phrase)) { warns.push(`答案包含兜底话术「${phrase}」`); break }
  }
  if (!pages.length) warns.push('未引用任何页码，来源无法验证')
  if (content.length < 50) warns.push('答案过短，推理可能不完整')
  return warns
}

function getStages(rp: RetrievalProcess) {
  return [
    { icon: '✏️', name: '改写', active: rp.query_rewrite_enabled, info: rp.query_rewrite_enabled ? (rp.rewritten_query ? '已改写' : '无需') : '关闭' },
    { icon: '🔄', name: 'Multi-Q', active: rp.multiquery_enabled, info: rp.multiquery_enabled ? `${rp.query_variants.length} 变体` : '关闭' },
    { icon: '🗃️', name: '检索', active: true, info: `${rp.pre_rerank_count} 候选` },
    { icon: '🗳️', name: 'Rerank', active: rp.rerank_applied, info: rp.rerank_applied ? `→${rp.post_rerank.length}` : '关闭' },
  ]
}

function scoreColor(s: number) {
  if (s > 0.7) return '#22c55e'
  if (s > 0.4) return '#f59e0b'
  return '#ef4444'
}

function setTab(idx: number, tab: 'pre' | 'post') { chunkTab.value[idx] = tab }

function fillSuggestion(s: string) { inputText.value = s; nextTick(() => sendQuestion()) }

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
      es.close(); streaming.value = false
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
    } catch { /* 普通 token */ }
    fullText += e.data
    qaStore.updateLast({ content: fullText })
  }

  es.addEventListener('meta', (e: MessageEvent) => {
    try {
      const meta = JSON.parse(e.data)
      pages = meta.pages ?? []
      const patch: Partial<Message> = { pages }
      if (meta.retrieval_process) patch.retrievalProcess = meta.retrieval_process
      qaStore.updateLast(patch)
    } catch { /* ignore */ }
  })

  es.onerror = () => {
    es.close(); streaming.value = false
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
  await qaApi.feedback({ query, answer: msg.content, feedback: type, config_name: configName.value, pages: msg.pages ?? [] }).catch(() => {})
  qaStore.updateAt(idx, { feedbackDone: true })
  ElMessage.success(type === 'good' ? '感谢反馈！' : '已记录，我们会改进')
}

function openBadForm(msg: Message, idx: number) {
  qaStore.updateAt(idx, { showBadForm: true, badForm: { error_type: '', correct_answer: '', comment: '' } })
}

async function submitBadFeedback(msg: Message, idx: number) {
  const query = getUserQuery(msg)
  await qaApi.feedback({ query, answer: msg.content, feedback: 'bad', config_name: configName.value, pages: msg.pages ?? [], error_type: msg.badForm?.error_type, correct_answer: msg.badForm?.correct_answer, comment: msg.badForm?.comment }).catch(() => {})
  qaStore.updateAt(idx, { feedbackDone: true, showBadForm: false })
  ElMessage.success('感谢您的详细反馈！')
}
</script>

<style scoped>
/* ── Layout ── */
.chat-layout {
  display: flex; flex-direction: column; height: 100%;
  background: #f8fafc; overflow: hidden;
}

/* ── Topbar ── */
.chat-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; background: #fff;
  border-bottom: 1px solid #e8edf3;
  flex-shrink: 0; gap: 12px;
  box-shadow: 0 1px 0 rgba(0,0,0,.04);
}
.topbar-left { display: flex; align-items: center; gap: 10px; }
.config-badge {
  display: flex; align-items: center; gap: 5px;
  padding: 3px 10px; border-radius: 20px;
  background: #eff6ff; border: 1px solid #bfdbfe;
  font-size: 12px; font-weight: 600; color: #2563eb;
}
.config-dot { width: 6px; height: 6px; border-radius: 50%; background: #3b82f6; }
.override-dot { font-size: 10px; color: #f59e0b; }
.clear-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 12px; border-radius: 8px; border: 1px solid #e2e8f0;
  background: #fff; color: #64748b; font-size: 12px; font-weight: 500;
  cursor: pointer; transition: all .16s;
}
.clear-btn:hover { background: #fef2f2; border-color: #fca5a5; color: #ef4444; }

/* ── Messages ── */
.messages {
  flex: 1; overflow-y: auto; padding: 24px 20px;
  display: flex; flex-direction: column; gap: 20px;
}

/* Empty state */
.empty-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: #94a3b8; padding: 60px 20px; text-align: center;
}
.empty-icon { font-size: 48px; margin-bottom: 16px; }
.empty-state h3 { font-size: 18px; font-weight: 600; color: #475569; margin: 0 0 8px; }
.empty-state p { font-size: 14px; color: #94a3b8; margin: 0 0 24px; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; max-width: 520px; }
.sugg-chip {
  padding: 7px 14px; border-radius: 20px;
  border: 1px solid #e2e8f0; background: #fff;
  color: #475569; font-size: 13px; cursor: pointer;
  transition: all .16s; white-space: nowrap;
}
.sugg-chip:hover { background: #eff6ff; border-color: #93c5fd; color: #2563eb; }

/* Message rows */
.msg-row { display: flex; gap: 10px; max-width: 880px; }
.msg-row.user { flex-direction: row-reverse; align-self: flex-end; }
.msg-row.ai { align-self: flex-start; }

/* Avatars */
.avatar {
  width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.user-av {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
}
.ai-av {
  background: linear-gradient(135deg, #0ea5e9, #06b6d4);
  color: #fff; font-size: 11px;
}

/* User bubble */
.msg-bubble.user-bubble {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  color: #fff; border-radius: 18px 4px 18px 18px;
  padding: 10px 16px; font-size: 14px; line-height: 1.6;
  max-width: 600px; word-break: break-word;
  box-shadow: 0 2px 8px rgba(59,130,246,.25);
}

/* AI card */
.msg-card {
  background: #fff; border-radius: 4px 18px 18px 18px;
  padding: 14px 18px; max-width: 700px;
  box-shadow: 0 2px 8px rgba(0,0,0,.07);
  border: 1px solid #f0f4f8;
}

/* Typing animation */
.typing { display: flex; gap: 4px; align-items: center; padding: 4px 0; }
.typing span {
  width: 7px; height: 7px; border-radius: 50%; background: #94a3b8;
  animation: bounce 1.2s infinite ease-in-out;
}
.typing span:nth-child(2) { animation-delay: .2s; }
.typing span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

/* Streaming cursor */
.cursor { animation: blink .8s infinite; color: #3b82f6; font-size: 15px; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

/* Warnings */
.warnings { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.warn-item {
  font-size: 12px; color: #92400e; background: #fffbeb;
  border: 1px solid #fde68a; border-radius: 6px; padding: 5px 10px;
  display: flex; align-items: center; gap: 5px;
}

/* Pages ref */
.pages-ref {
  display: flex; align-items: center; gap: 5px;
  margin-top: 10px; font-size: 12px; color: #64748b;
  background: #f8fafc; border-radius: 6px; padding: 5px 10px;
}
.ref-icon { font-size: 13px; }

/* ── 检索过程 ── */
.retrieval-details { margin-top: 12px; }
.retrieval-summary {
  font-size: 12px; color: #64748b; cursor: pointer; list-style: none;
  padding: 5px 10px; border-radius: 6px; background: #f1f5f9;
  display: inline-flex; align-items: center; gap: 5px;
  transition: background .16s; user-select: none;
}
.retrieval-summary:hover { background: #e2e8f0; color: #334155; }
.retrieval-body { padding: 12px 0 4px; display: flex; flex-direction: column; gap: 10px; }

/* Stage flow */
.stage-row { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.stage-wrap { display: flex; align-items: center; gap: 4px; }
.stage-node {
  display: flex; flex-direction: column; align-items: center; gap: 1px;
  padding: 6px 10px; border-radius: 8px;
  border: 1px solid #e2e8f0; min-width: 68px; text-align: center;
}
.stage-node.active { background: #f0fdf4; border-color: #bbf7d0; }
.stage-node.inactive { background: #f8fafc; border-color: #e2e8f0; opacity: .55; }
.stage-em { font-size: 14px; }
.stage-name { font-size: 10px; font-weight: 600; color: #334155; }
.stage-info { font-size: 9px; color: #94a3b8; }
.stage-arrow { color: #cbd5e1; font-size: 18px; font-weight: 300; }

/* Rewrite box */
.rewrite-box {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  background: #f8fafc; border-radius: 8px; padding: 8px 12px;
  font-size: 12px;
}
.rw-label { font-size: 10px; font-weight: 600; color: #94a3b8; text-transform: uppercase; flex-shrink: 0; }
.rw-text { flex: 1; min-width: 100px; }
.rw-text.muted { color: #64748b; }
.rw-text.accent { color: #2563eb; font-weight: 500; }
.rw-arrow { color: #94a3b8; font-size: 16px; flex-shrink: 0; }

/* Variants */
.variants-box { background: #f8fafc; border-radius: 8px; padding: 8px 12px; }
.box-title { font-size: 11px; font-weight: 600; color: #475569; margin-bottom: 6px; }
.variant-row { display: flex; align-items: flex-start; gap: 6px; margin-bottom: 4px; }
.v-idx {
  background: #3b82f6; color: #fff; border-radius: 10px;
  padding: 0 6px; font-size: 10px; line-height: 18px; flex-shrink: 0;
}
.v-text { font-size: 12px; color: #475569; }

/* Chunk tabs */
.chunk-tabs { border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }
.tab-bar { display: flex; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
.tab-btn {
  flex: 1; padding: 6px 10px; border: none; background: none;
  font-size: 11px; font-weight: 500; color: #94a3b8; cursor: pointer;
  transition: all .16s;
}
.tab-btn.active { color: #2563eb; background: #fff; border-bottom: 2px solid #3b82f6; }
.chunk-list { max-height: 220px; overflow-y: auto; }
.chunk-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 8px 10px; border-bottom: 1px solid #f1f5f9;
  transition: background .1s;
}
.chunk-row:last-child { border-bottom: none; }
.chunk-row:hover { background: #f8fafc; }
.chunk-row.top { background: #f0fdf4; }
.chunk-rank { font-size: 14px; flex-shrink: 0; width: 20px; text-align: center; margin-top: 1px; }
.chunk-info { flex: 1; min-width: 0; }
.chunk-id {
  font-family: monospace; font-size: 10px; color: #3b82f6;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 2px;
}
.chunk-snippet {
  font-size: 11px; color: #64748b;
  white-space: pre-wrap; word-break: break-all;
}
.chunk-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; flex-shrink: 0; }
.chunk-score { font-size: 11px; font-weight: 700; }
.chunk-page { font-size: 10px; color: #94a3b8; background: #f1f5f9; padding: 1px 5px; border-radius: 4px; }

/* ── Feedback ── */
.feedback-row { display: flex; align-items: center; gap: 6px; margin-top: 12px; flex-wrap: wrap; }
.feedback-done { font-size: 12px; color: #22c55e; background: #f0fdf4; padding: 3px 10px; border-radius: 20px; }
.fb-btn {
  padding: 4px 12px; border-radius: 20px; border: 1px solid #e2e8f0;
  font-size: 12px; cursor: pointer; transition: all .16s; font-weight: 500;
}
.fb-btn.good { background: #fff; color: #475569; }
.fb-btn.good:hover { background: #f0fdf4; border-color: #86efac; color: #16a34a; }
.fb-btn.bad { background: #fff; color: #475569; }
.fb-btn.bad:hover { background: #fef2f2; border-color: #fca5a5; color: #ef4444; }

.bad-form {
  width: 100%; margin-top: 10px; padding: 14px 16px;
  background: #fff9f9; border: 1px solid #fecaca; border-radius: 10px;
}
.bad-form-title { font-size: 13px; font-weight: 600; color: #ef4444; margin-bottom: 10px; }

/* ── Input area ── */
.input-wrap {
  padding: 14px 20px 16px; background: #fff;
  border-top: 1px solid #e8edf3; flex-shrink: 0;
}
.input-box {
  display: flex; align-items: center; gap: 8px;
  background: #f8fafc; border: 1.5px solid #e2e8f0;
  border-radius: 14px; padding: 4px 4px 4px 14px;
  transition: border-color .18s, box-shadow .18s;
}
.input-box.focused { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,.1); }
.chat-input { flex: 1; }
:deep(.chat-input .el-input__wrapper) {
  background: transparent !important; box-shadow: none !important;
  border: none !important; padding: 0;
}
:deep(.chat-input .el-input__inner) { font-size: 14px; color: #1e293b; }
.send-btn {
  width: 36px; height: 36px; border-radius: 10px; border: none;
  background: #e2e8f0; color: #94a3b8; font-size: 16px; font-weight: 700;
  cursor: pointer; transition: all .16s; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.send-btn.active { background: #3b82f6; color: #fff; box-shadow: 0 2px 8px rgba(59,130,246,.3); }
.send-btn:disabled { opacity: .5; cursor: not-allowed; }
.input-hint { font-size: 11px; color: #cbd5e1; margin-top: 6px; text-align: center; }
</style>
