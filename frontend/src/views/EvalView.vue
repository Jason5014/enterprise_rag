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
            <el-option label="BASE（基础）" value="base" />
            <el-option label="FAST（快速）" value="fast" />
            <el-option label="PRECISION（高精度）" value="precision" />
            <el-option label="FULL（完整）" value="full" />
          </el-select>
        </el-form-item>
        <el-form-item label="LLM 评分">
          <el-switch v-model="form.enable_llm_eval" active-text="开启" inactive-text="关闭" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="running" @click="runEval" :icon="VideoPlay">
            {{ running ? '评估中...' : '开始评估' }}
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 测试集信息 -->
      <div v-if="evalInfo" style="margin-top:8px; color:#909399; font-size:13px;">
        测试集：{{ evalInfo.total }} 题
        <el-tag v-if="evalInfo.has_ground_truth" size="small" type="success" effect="plain" style="margin-left:8px;">
          含 Ground Truth
        </el-tag>
        <el-tag v-else size="small" type="info" effect="plain" style="margin-left:8px;">
          无 Ground Truth（不计算检索指标）
        </el-tag>
        <span v-if="evalInfo.total > 0" style="margin-left:12px;">
          示例：{{ evalInfo.questions?.slice(0, 2).join(' / ') }}
          <span v-if="evalInfo.total > 2">...</span>
        </span>
      </div>

      <!-- 进度 -->
      <div v-if="running || progressMsg" style="margin-top:12px;">
        <el-progress :percentage="progress" :status="progressStatus" style="margin-bottom:4px;" />
        <div style="font-size:13px; color:#909399;">{{ progressMsg }}</div>
      </div>
    </el-card>

    <!-- 本次评估指标概览 -->
    <template v-if="latestMetrics">
      <div style="font-size:15px; font-weight:600; margin-bottom:10px; color:#303133;">
        📊 评估指标（共 {{ results.length }} 题，平均延迟 {{ avgLatency }} ms）
      </div>

      <!-- 总分 -->
      <el-card shadow="never" style="margin-bottom:16px; background:linear-gradient(135deg,#409eff11,#67c23a11); border-color:#dce7fd;">
        <div style="display:flex; align-items:center; gap:20px;">
          <div style="text-align:center;">
            <div style="font-size:42px; font-weight:700; color:#409eff;">{{ overallScore }}</div>
            <div style="font-size:13px; color:#909399;">综合得分 / 100</div>
          </div>
          <el-divider direction="vertical" style="height:60px;" />
          <div style="flex:1; display:grid; grid-template-columns:repeat(4,1fr); gap:10px;">
            <div v-for="m in metricCards" :key="m.key" class="metric-cell">
              <div class="metric-val" :style="{ color: metricColor(m.val) }">{{ fmt(m.val) }}</div>
              <div class="metric-label">{{ m.label }}</div>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 指标分组：检索 vs 生成 -->
      <el-row :gutter="12" style="margin-bottom:16px;">
        <el-col :span="12">
          <el-card shadow="never">
            <template #header><span style="font-size:13px; color:#606266;">🔍 检索质量</span></template>
            <div class="metrics-grid">
              <div v-for="m in retrievalMetrics" :key="m.key" class="metric-cell">
                <div class="metric-val" :style="{ color: metricColor(m.val) }">{{ fmt(m.val) }}</div>
                <div class="metric-label">{{ m.label }}</div>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <template #header><span style="font-size:13px; color:#606266;">💡 排序质量</span></template>
            <div class="metrics-grid">
              <div v-for="m in rankingMetrics" :key="m.key" class="metric-cell">
                <div class="metric-val" :style="{ color: metricColor(m.val) }">{{ fmt(m.val) }}</div>
                <div class="metric-label">{{ m.label }}</div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- 逐题结果 -->
    <el-card v-if="results.length > 0" style="margin-bottom:16px;">
      <template #header>
        <div style="display:flex; align-items:center; gap:12px;">
          <span>逐题结果</span>
          <el-tag size="small" type="info" effect="plain">
            命中率 {{ hitRate }}%（Top-5）
          </el-tag>
        </div>
      </template>
      <el-table :data="results" stripe style="width:100%;" row-key="question" @expand-change="() => {}">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div style="padding:12px 24px; background:#fafafa; line-height:1.8;">
              <div v-if="row.answer && row.answer !== 'ERROR'">
                <div style="font-size:13px; font-weight:600; color:#303133; margin-bottom:6px;">答案</div>
                <div style="font-size:13px; color:#606266; white-space:pre-wrap;">{{ row.answer }}</div>
              </div>
              <div v-if="row.retrieved_ids?.length" style="margin-top:10px;">
                <div style="font-size:12px; font-weight:600; color:#909399;">检索块 ID（Top-{{ row.retrieved_ids.length }}）</div>
                <div style="font-size:12px; color:#909399; word-break:break-all;">
                  <span v-for="(id, i) in row.retrieved_ids" :key="i"
                    :style="row.relevant_chunks?.includes(id) ? 'color:#67c23a; font-weight:600;' : 'color:#c0c4cc;'"
                    style="margin-right:8px;">
                    {{ id.slice(-12) }}
                  </span>
                </div>
                <div style="font-size:12px; color:#909399; margin-top:4px;">
                  <span style="color:#67c23a;">■</span> 相关块
                  <span style="color:#c0c4cc; margin-left:8px;">■</span> 不相关块
                </div>
              </div>
              <div v-if="row.error" style="color:#f56c6c; font-size:13px;">错误：{{ row.error }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column type="index" width="50" />
        <el-table-column label="问题" prop="question" min-width="220" show-overflow-tooltip />
        <el-table-column label="类别" prop="category" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.category" size="small" effect="plain">{{ row.category }}</el-tag>
            <span v-else style="color:#c0c4cc;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="引用页" width="90" align="center">
          <template #default="{ row }">{{ (row.pages ?? []).join(', ') || '-' }}</template>
        </el-table-column>
        <el-table-column label="命中" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_hit === true" size="small" type="success" effect="dark">✓</el-tag>
            <el-tag v-else-if="row.is_hit === false" size="small" type="danger" effect="dark">✗</el-tag>
            <span v-else style="color:#c0c4cc;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="延迟(ms)" prop="latency_ms" width="90" align="right">
          <template #default="{ row }">
            <span :style="row.latency_ms > 3000 ? 'color:#f56c6c;' : row.latency_ms > 1500 ? 'color:#e6a23c;' : 'color:#67c23a;'">
              {{ row.latency_ms }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.answer === 'ERROR'" size="small" type="danger">失败</el-tag>
            <el-tag v-else size="small" type="success">完成</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 历史评估记录 -->
    <el-card>
      <template #header>
        <div style="display:flex; align-items:center;">
          <span>历史评估记录</span>
          <el-button text :icon="Refresh" @click="fetchHistory" style="margin-left:auto;" />
        </div>
      </template>
      <el-empty v-if="history.length === 0" description="暂无历史记录" />
      <el-table v-else :data="history" stripe style="width:100%;">
        <el-table-column label="时间" width="155">
          <template #default="{ row }">
            {{ (row.timestamp ?? '').slice(0, 16).replace('T', ' ') }}
          </template>
        </el-table-column>
        <el-table-column label="配置" prop="config_name" width="90">
          <template #default="{ row }">
            <el-tag size="small">{{ row.config_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="题数" prop="question_count" width="70" align="center" />
        <el-table-column label="Hit@1" width="75" align="center">
          <template #default="{ row }">{{ fmtHist(row.metrics?.['hit@1']) }}</template>
        </el-table-column>
        <el-table-column label="Hit@3" width="75" align="center">
          <template #default="{ row }">{{ fmtHist(row.metrics?.['hit@3']) }}</template>
        </el-table-column>
        <el-table-column label="Hit@5" width="75" align="center">
          <template #default="{ row }">{{ fmtHist(row.metrics?.['hit@5']) }}</template>
        </el-table-column>
        <el-table-column label="Recall@5" width="80" align="center">
          <template #default="{ row }">{{ fmtHist(row.metrics?.['recall@5']) }}</template>
        </el-table-column>
        <el-table-column label="MRR" width="75" align="center">
          <template #default="{ row }">{{ fmtHist(row.metrics?.['mrr']) }}</template>
        </el-table-column>
        <el-table-column label="NDCG@5" width="80" align="center">
          <template #default="{ row }">{{ fmtHist(row.metrics?.['ndcg@5']) }}</template>
        </el-table-column>
        <el-table-column label="平均延迟" width="90" align="right">
          <template #default="{ row }">
            <span v-if="row.metrics?.avg_latency_ms">{{ Math.round(row.metrics.avg_latency_ms) }} ms</span>
            <span v-else style="color:#c0c4cc;">-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { VideoPlay, Refresh } from '@element-plus/icons-vue'
import { kbApi } from '@/api/kb'
import http from '@/api/http'

const kbList = ref<any[]>([])
const form = ref({ kb_id: '', config_name: 'base', enable_llm_eval: false })
const running = ref(false)
const progress = ref(0)
const progressMsg = ref('')
const progressStatus = ref<'' | 'success' | 'exception'>('')
const results = ref<any[]>([])
const history = ref<any[]>([])
const evalInfo = ref<any>(null)
const latestMetrics = ref<Record<string, number> | null>(null)
const avgLatency = ref(0)

onMounted(async () => {
  try { const r = await kbApi.list(); kbList.value = r.data } catch { /* ignore */ }
  await Promise.all([fetchHistory(), fetchEvalInfo()])
})

async function fetchEvalInfo() {
  try { const r = await http.get('/eval/questions'); evalInfo.value = r.data } catch { /* ignore */ }
}

async function fetchHistory() {
  try { const r = await http.get('/eval/history?limit=20'); history.value = r.data } catch { /* ignore */ }
}

// ---- 指标展示 ----
const metricCards = computed(() => {
  if (!latestMetrics.value) return []
  const m = latestMetrics.value
  return [
    { key: 'hit@1', label: 'Hit@1', val: m['hit@1'] ?? 0 },
    { key: 'hit@3', label: 'Hit@3', val: m['hit@3'] ?? 0 },
    { key: 'hit@5', label: 'Hit@5', val: m['hit@5'] ?? 0 },
    { key: 'recall@5', label: 'Recall@5', val: m['recall@5'] ?? 0 },
  ]
})

const retrievalMetrics = computed(() => {
  if (!latestMetrics.value) return []
  const m = latestMetrics.value
  return [
    { key: 'recall@1', label: 'Recall@1', val: m['recall@1'] ?? 0 },
    { key: 'recall@3', label: 'Recall@3', val: m['recall@3'] ?? 0 },
    { key: 'recall@5', label: 'Recall@5', val: m['recall@5'] ?? 0 },
  ]
})

const rankingMetrics = computed(() => {
  if (!latestMetrics.value) return []
  const m = latestMetrics.value
  return [
    { key: 'mrr', label: 'MRR', val: m['mrr'] ?? 0 },
    { key: 'ndcg@5', label: 'NDCG@5', val: m['ndcg@5'] ?? 0 },
    { key: 'hit@5', label: 'Hit@5', val: m['hit@5'] ?? 0 },
  ]
})

const overallScore = computed(() => {
  if (!latestMetrics.value) return 0
  const m = latestMetrics.value
  const vals = [m['hit@5'], m['recall@5'], m['mrr'], m['ndcg@5']].filter(v => v !== undefined && v !== null)
  if (!vals.length) return 0
  return Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100)
})

const hitRate = computed(() => {
  if (!results.value.length) return 0
  const withHit = results.value.filter(r => r.is_hit !== undefined)
  if (!withHit.length) return '-'
  return Math.round(withHit.filter(r => r.is_hit).length / withHit.length * 100)
})

function fmt(val: number): string {
  if (val === undefined || val === null) return '-'
  return (val * 100).toFixed(1) + '%'
}

function fmtHist(val: number | undefined): string {
  if (val === undefined || val === null) return '-'
  return (val * 100).toFixed(1) + '%'
}

function metricColor(val: number): string {
  if (val === undefined || val === null) return '#909399'
  if (val >= 0.8) return '#67c23a'
  if (val >= 0.6) return '#409eff'
  if (val >= 0.4) return '#e6a23c'
  return '#f56c6c'
}

async function runEval() {
  running.value = true
  progress.value = 0
  progressMsg.value = '连接中...'
  results.value = []
  latestMetrics.value = null
  progressStatus.value = ''

  const token = localStorage.getItem('token') ?? ''
  const body = {
    config_name: form.value.config_name,
    kb_id: form.value.kb_id || undefined,
    enable_llm_eval: form.value.enable_llm_eval,
  }

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
          if (evt.stage === 'start') {
            progressMsg.value = `共 ${evt.total} 题${evt.has_ground_truth ? '（含 Ground Truth）' : ''}`
          } else if (evt.stage === 'progress') {
            progress.value = Math.round((evt.current / evt.total) * 100)
            progressMsg.value = `[${evt.current}/${evt.total}] ${evt.question}`
          } else if (evt.stage === 'done') {
            progress.value = 100
            progressStatus.value = 'success'
            progressMsg.value = `评估完成，平均延迟 ${evt.avg_latency_ms} ms`
            results.value = evt.results
            latestMetrics.value = evt.metrics
            avgLatency.value = Math.round(evt.avg_latency_ms)
            await fetchHistory()
          } else if (evt.stage === 'error') {
            progressStatus.value = 'exception'
            progressMsg.value = evt.message
          }
        } catch { /* ignore parse errors */ }
      }
    }
  } catch (e: any) {
    progressStatus.value = 'exception'
    progressMsg.value = e.message
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.page-container { padding: 24px; height: 100%; overflow-y: auto; box-sizing: border-box; }
.page-header { display: flex; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; }

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.metric-cell {
  text-align: center;
  padding: 8px 4px;
}

.metric-val {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}

.metric-label {
  font-size: 11px;
  color: #909399;
  margin-top: 2px;
}
</style>
