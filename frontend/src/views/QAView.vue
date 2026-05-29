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

          <!-- 推理过程折叠 -->
          <el-collapse v-if="msg.role === 'assistant' && !msg.loading && msg.content"
            style="margin-top:8px; border:none;">
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
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Promotion, ChatDotRound, Document, CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { kbApi } from '@/api/kb'
import { qaApi } from '@/api/qa'
import { useQAStore, type Message } from '@/stores/qa'
import { useConfigStore, CONFIG_LABELS } from '@/stores/config'

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

  // 元数据事件（pages、chunk_count）
  es.addEventListener('meta', (e: MessageEvent) => {
    try {
      const meta = JSON.parse(e.data)
      pages = meta.pages ?? []
      qaStore.updateLast({ pages })
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
  display: flex; gap: 10px; max-width: 860px;
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
  box-shadow: 0 1px 4px rgba(0,0,0,.06); max-width: 720px; line-height: 1.7;
}
.message-row.user .bubble { background: #ecf5ff; }
.typing-dot { animation: blink 1s infinite; color: #909399; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
.input-area {
  padding: 14px 20px; background: #fff; border-top: 1px solid #ebeef5;
  display: flex; align-items: center; gap: 10px; flex-shrink: 0;
}
</style>
