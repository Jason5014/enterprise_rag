<template>
  <div class="qa-layout">
    <!-- 顶部工具栏 -->
    <div class="qa-toolbar">
      <el-select v-model="activeKBId" placeholder="选择知识库（默认内置）" clearable
        style="width:220px;" @change="qaStore.clearHistory()">
        <el-option v-for="kb in kbList" :key="kb.kb_id" :label="kb.name" :value="kb.kb_id" />
      </el-select>
      <el-button text @click="clearHistory" :icon="Delete" style="margin-left:8px;">清空对话</el-button>
    </div>

    <!-- 消息区 -->
    <div class="messages" ref="messagesEl">
      <div v-if="messages.length === 0" class="empty-hint">
        <el-icon size="48" color="#c0c4cc"><ChatDotRound /></el-icon>
        <p>向知识库提问吧 👆</p>
      </div>

      <div v-for="(msg, i) in messages" :key="i" :class="['message-row', msg.role]">
        <div class="avatar">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
        <div class="bubble">
          <!-- 流式加载中 -->
          <span v-if="msg.loading && !msg.content" class="typing-dot">●●●</span>
          <span v-else style="white-space:pre-wrap; word-break:break-word;">{{ msg.content }}</span>

          <!-- 推理过程折叠（仅 assistant） -->
          <el-collapse v-if="msg.role === 'assistant' && msg.analysis" style="margin-top:10px; border:none;">
            <el-collapse-item name="a">
              <template #title>
                <span style="font-size:12px; color:#909399;">📖 查看推理过程</span>
              </template>
              <div style="font-size:13px; color:#606266; white-space:pre-wrap;">{{ msg.analysis }}</div>
            </el-collapse-item>
          </el-collapse>

          <!-- 页码 -->
          <div v-if="msg.pages && msg.pages.length > 0" style="margin-top:6px; font-size:12px; color:#909399;">
            引用页码：{{ msg.pages.join(', ') }}
          </div>

          <!-- 反馈按钮 -->
          <div v-if="msg.role === 'assistant' && !msg.loading && msg.content"
            style="margin-top:8px; display:flex; gap:8px;">
            <el-button text size="small" @click="sendFeedback(msg, 'good')">👍</el-button>
            <el-button text size="small" @click="sendFeedback(msg, 'bad')">👎</el-button>
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
          <el-button
            type="primary"
            :icon="Promotion"
            :loading="streaming"
            @click="sendQuestion"
            circle
          />
        </template>
      </el-input>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Promotion } from '@element-plus/icons-vue'
import { kbApi } from '@/api/kb'
import { qaApi, createQAStream } from '@/api/qa'
import { useQAStore, type Message } from '@/stores/qa'

const qaStore = useQAStore()
const messages = computed(() => qaStore.messages)
const activeKBId = ref<string | null>(null)
const inputText = ref('')
const streaming = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
const kbList = ref<any[]>([])

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
  qaStore.addMessage({ role: 'assistant', content: '', loading: true })

  streaming.value = true
  const es = createQAStream(q, activeKBId.value ?? undefined)

  let fullText = ''
  es.onmessage = (e) => {
    if (e.data === '[DONE]') {
      es.close()
      streaming.value = false
      qaStore.updateLast({ loading: false, content: fullText || '（空响应）' })
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

function sendFeedback(msg: Message, type: 'good' | 'bad') {
  const userMsg = messages.value
    .slice(0, messages.value.indexOf(msg))
    .reverse()
    .find(m => m.role === 'user')
  if (!userMsg) return
  qaApi.feedback({ query: userMsg.content, answer: msg.content, feedback: type })
    .then(() => ElMessage.success(type === 'good' ? '感谢反馈！' : '已记录，我们会改进'))
    .catch(() => {})
}
</script>

<style scoped>
.qa-layout {
  display: flex; flex-direction: column; height: 100%;
  background: #f5f7fa; overflow: hidden;
}
.qa-toolbar {
  padding: 12px 20px; background: #fff; border-bottom: 1px solid #ebeef5;
  display: flex; align-items: center;
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
  display: flex; gap: 10px; max-width: 820px;
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
  box-shadow: 0 1px 4px rgba(0,0,0,.06); max-width: 680px; line-height: 1.7;
}
.message-row.user .bubble { background: #ecf5ff; }
.typing-dot { animation: blink 1s infinite; color: #909399; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
.input-area {
  padding: 14px 20px; background: #fff; border-top: 1px solid #ebeef5;
  display: flex; align-items: center; gap: 10px;
}
</style>
