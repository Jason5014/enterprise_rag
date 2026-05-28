<template>
  <div class="page-container">
    <div class="page-header">
      <h2>评估测试</h2>
    </div>

    <!-- 配置面板 -->
    <el-card style="margin-bottom:16px;">
      <el-form :inline="true" :model="form">
        <el-form-item label="知识库">
          <el-select v-model="form.kb_id" placeholder="默认内置" clearable style="width:200px;">
            <el-option v-for="kb in kbList" :key="kb.kb_id" :label="kb.name" :value="kb.kb_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="配置">
          <el-select v-model="form.config_name" style="width:140px;">
            <el-option label="base" value="base" />
            <el-option label="fast" value="fast" />
            <el-option label="precision" value="precision" />
            <el-option label="full" value="full" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="runEval" :icon="VideoPlay">
            {{ running ? '评估中...' : '开始评估' }}
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 进度 -->
      <div v-if="running || progressMsg">
        <el-progress :percentage="progress" :status="progressStatus" style="margin:10px 0 4px;" />
        <div style="font-size:13px; color:#909399;">{{ progressMsg }}</div>
      </div>
    </el-card>

    <!-- 评估结果 -->
    <el-card v-if="results.length > 0">
      <template #header>
        <span>评估结果（本次 {{ results.length }} 题）</span>
      </template>
      <el-table :data="results" stripe style="width:100%;">
        <el-table-column type="index" width="50" />
        <el-table-column label="问题" prop="question" min-width="200" />
        <el-table-column label="答案" prop="answer" min-width="300">
          <template #default="{ row }">
            <span :style="row.answer === 'N/A' || row.answer === 'ERROR' ? 'color:#f56c6c;' : ''">
              {{ row.answer }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="引用页" width="100">
          <template #default="{ row }">{{ (row.pages ?? []).join(', ') || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 历史记录 -->
    <el-card style="margin-top:16px;">
      <template #header>
        <span>历史评估记录</span>
        <el-button text :icon="Refresh" @click="fetchHistory" style="float:right;" />
      </template>
      <el-empty v-if="history.length === 0" description="暂无历史记录" />
      <el-timeline v-else>
        <el-timeline-item
          v-for="h in history" :key="h.eval_id"
          :timestamp="(h.timestamp ?? '').slice(0,16).replace('T',' ')"
          type="primary"
        >
          <el-tag>{{ h.config_name }}</el-tag>
          <span style="margin-left:8px; color:#606266; font-size:13px;">
            共 {{ h.question_count }} 题
          </span>
        </el-timeline-item>
      </el-timeline>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { VideoPlay, Refresh } from '@element-plus/icons-vue'
import { kbApi } from '@/api/kb'
import http from '@/api/http'

const kbList = ref<any[]>([])
const form = ref({ kb_id: '', config_name: 'base' })
const running = ref(false)
const progress = ref(0)
const progressMsg = ref('')
const progressStatus = ref<'' | 'success' | 'exception'>('')
const results = ref<any[]>([])
const history = ref<any[]>([])

onMounted(async () => {
  try { const r = await kbApi.list(); kbList.value = r.data } catch { /* ignore */ }
  await fetchHistory()
})

async function fetchHistory() {
  try { const r = await http.get('/eval/history?limit=20'); history.value = r.data } catch { /* ignore */ }
}

async function runEval() {
  running.value = true; progress.value = 0; progressMsg.value = '连接中...'; results.value = []
  progressStatus.value = ''

  const token = localStorage.getItem('token') ?? ''
  const body = { config_name: form.value.config_name, kb_id: form.value.kb_id || undefined }

  try {
    const resp = await fetch('/api/eval/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    })

    const reader = resp.body!.getReader()
    const dec = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        try {
          const evt = JSON.parse(raw)
          if (evt.stage === 'start') { progressMsg.value = `共 ${evt.total} 题` }
          else if (evt.stage === 'progress') {
            progress.value = Math.round((evt.current / evt.total) * 100)
            progressMsg.value = `[${evt.current}/${evt.total}] ${evt.question}`
          } else if (evt.stage === 'done') {
            progress.value = 100; progressStatus.value = 'success'
            progressMsg.value = '评估完成'
            results.value = evt.results
            await fetchHistory()
          } else if (evt.stage === 'error') {
            progressStatus.value = 'exception'
            progressMsg.value = evt.message
          }
        } catch { /* ignore parse errors */ }
      }
    }
  } catch (e: any) {
    progressStatus.value = 'exception'; progressMsg.value = e.message
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.page-container { padding: 24px; height: 100%; overflow-y: auto; box-sizing: border-box; }
.page-header { display: flex; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; }
</style>
