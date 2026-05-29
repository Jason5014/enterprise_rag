<template>
  <div class="page-container">
    <div class="page-header">
      <h2>质量监控</h2>
      <el-button :icon="Refresh" @click="fetchAll">刷新</el-button>
    </div>

    <!-- 概览统计 -->
    <el-row :gutter="16" style="margin-bottom:20px;">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="总问答次数" :value="stats.total" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="好评次数" :value="stats.good">
            <template #suffix><span style="color:#67c23a; font-size:14px;"> 👍</span></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="差评次数" :value="stats.bad">
            <template #suffix><span style="color:#f56c6c; font-size:14px;"> 👎</span></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="好评率" :value="stats.good_rate" suffix="%" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-bottom:20px;">
      <!-- 错误类型分析 -->
      <el-col :span="12">
        <el-card style="height:100%;">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between;">
              <span>🔍 错误类型分布</span>
              <el-tag size="small" type="danger" effect="plain">
                Bad Case 共 {{ analysis.total_bad ?? 0 }} 条
              </el-tag>
            </div>
          </template>

          <el-empty v-if="!analysis.error_types || !Object.keys(analysis.error_types).length"
            description="暂无 Bad Case 数据" :image-size="60" />

          <div v-else>
            <div v-for="(cnt, etype) in analysis.error_types" :key="etype" class="error-row">
              <div class="error-info">
                <el-tag :type="errorTagType(etype)" size="small" effect="light">
                  {{ errorLabel(etype) }}
                </el-tag>
                <span style="font-size:12px; color:#909399; margin-left:6px;">
                  {{ errorStage(etype) }}
                </span>
              </div>
              <div class="error-bar-wrap">
                <div class="error-bar"
                  :style="{ width: barPct(cnt, analysis.total_bad) + '%', background: errorColor(etype) }" />
              </div>
              <span class="error-count">{{ cnt }}</span>
            </div>

            <!-- 示例查询 -->
            <el-collapse style="margin-top:12px; border:none;">
              <el-collapse-item v-for="(queries, etype) in analysis.error_queries" :key="etype" :name="etype">
                <template #title>
                  <span style="font-size:12px; color:#909399;">
                    {{ errorLabel(etype) }} 示例问题
                  </span>
                </template>
                <ul style="margin:0; padding-left:16px; font-size:12px; color:#606266;">
                  <li v-for="(q, i) in queries" :key="i">{{ q }}</li>
                </ul>
              </el-collapse-item>
            </el-collapse>
          </div>
        </el-card>
      </el-col>

      <!-- 阶段分布 & 配置对比 -->
      <el-col :span="12">
        <el-card style="margin-bottom:12px;">
          <template #header><span>⚙️ Pipeline 阶段分布</span></template>
          <el-empty v-if="!analysis.stage_distribution || !Object.keys(analysis.stage_distribution).length"
            description="暂无数据" :image-size="60" />
          <div v-else>
            <div v-for="(cnt, stage) in analysis.stage_distribution" :key="stage" class="error-row">
              <el-tag size="small" effect="plain">{{ stageLabel(stage) }}</el-tag>
              <div class="error-bar-wrap">
                <div class="error-bar"
                  :style="{ width: barPct(cnt, analysis.total_bad) + '%', background: '#409eff' }" />
              </div>
              <span class="error-count">{{ cnt }}</span>
            </div>
          </div>
        </el-card>

        <el-card>
          <template #header><span>📈 各配置好评率</span></template>
          <el-empty v-if="!analysis.by_config || !Object.keys(analysis.by_config).length"
            description="暂无数据" :image-size="60" />
          <el-table v-else :data="byConfigRows" size="small">
            <el-table-column label="配置" prop="name" width="90">
              <template #default="{ row }">
                <el-tag size="small">{{ row.name }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="总数" prop="total" width="65" align="center" />
            <el-table-column label="好评" prop="helpful" width="65" align="center" />
            <el-table-column label="好评率">
              <template #default="{ row }">
                <el-progress :percentage="row.good_rate" :color="rateColor(row.good_rate)"
                  :stroke-width="8" style="width:100%;" />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 优化建议 -->
    <el-card v-if="suggestions.length > 0" style="margin-bottom:20px;">
      <template #header><span>💡 优化建议</span></template>
      <div v-for="(sug, i) in suggestions" :key="i" class="suggestion-row">
        <el-icon :color="sug.color"><component :is="sug.icon" /></el-icon>
        <div>
          <div style="font-size:13px; font-weight:600; color:#303133;">{{ sug.title }}</div>
          <div style="font-size:12px; color:#606266; margin-top:2px;">{{ sug.desc }}</div>
        </div>
      </div>
    </el-card>

    <!-- Bad Case 列表 -->
    <el-card>
      <template #header>
        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
          <span>Bad Case 列表</span>
          <el-input v-model="keyword" placeholder="关键词筛选" clearable style="width:160px;"
            @change="() => { page = 1; fetchBadCases() }" />
          <el-select v-model="filterErrorType" placeholder="错误类型" clearable style="width:140px;"
            @change="() => { page = 1; fetchBadCases() }">
            <el-option label="幻觉" value="hallucination" />
            <el-option label="不相关" value="irrelevant" />
            <el-option label="不完整" value="incomplete" />
            <el-option label="事实错误" value="factual_error" />
            <el-option label="过时" value="outdated" />
            <el-option label="其他" value="other" />
          </el-select>
          <el-select v-model="filterConfig" placeholder="配置" clearable style="width:110px;"
            @change="() => { page = 1; fetchBadCases() }">
            <el-option label="base" value="base" />
            <el-option label="fast" value="fast" />
            <el-option label="precision" value="precision" />
            <el-option label="full" value="full" />
          </el-select>
          <div style="margin-left:auto; display:flex; gap:8px;">
            <el-button :icon="Plus" @click="addToEval" :loading="addingToEval" type="success" plain>
              加入评测集
            </el-button>
            <el-button :icon="Download" @click="exportBadCases">导出 JSONL</el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="badCases.length === 0" description="暂无 Bad Case" />

      <el-table v-else :data="badCases" stripe style="width:100%;" row-key="timestamp">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div style="padding:12px 24px; background:#fafafa; font-size:13px; line-height:1.8;">
              <el-row :gutter="16">
                <el-col :span="12">
                  <div style="font-weight:600; color:#303133; margin-bottom:4px;">问题</div>
                  <div style="color:#606266;">{{ row.query }}</div>
                  <div style="font-weight:600; color:#303133; margin-top:10px; margin-bottom:4px;">答案</div>
                  <div style="color:#606266; white-space:pre-wrap;">{{ row.answer }}</div>
                </el-col>
                <el-col :span="12">
                  <template v-if="row.user_feedback?.correct_answer">
                    <div style="font-weight:600; color:#67c23a; margin-bottom:4px;">✅ 正确答案</div>
                    <div style="color:#606266;">{{ row.user_feedback.correct_answer }}</div>
                  </template>
                  <template v-if="row.user_feedback?.comment">
                    <div style="font-weight:600; color:#303133; margin-top:10px; margin-bottom:4px;">补充说明</div>
                    <div style="color:#606266;">{{ row.user_feedback.comment }}</div>
                  </template>
                  <template v-if="row.relevant_pages?.length">
                    <div style="font-weight:600; color:#303133; margin-top:10px; margin-bottom:4px;">引用页码</div>
                    <div style="color:#909399;">{{ row.relevant_pages.join(', ') }}</div>
                  </template>
                  <!-- 优化建议 -->
                  <div style="margin-top:10px;">
                    <el-tag size="small" effect="plain" style="margin-right:4px;">
                      阶段：{{ stageLabel(errorStage(row.user_feedback?.error_type)) }}
                    </el-tag>
                    <div style="font-size:12px; color:#909399; margin-top:4px;">
                      {{ optimizationHint(row.user_feedback?.error_type) }}
                    </div>
                  </div>
                </el-col>
              </el-row>
            </div>
          </template>
        </el-table-column>

        <el-table-column type="index" width="50" />
        <el-table-column label="问题" prop="query" min-width="200" show-overflow-tooltip />
        <el-table-column label="错误类型" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.user_feedback?.error_type"
              :type="errorTagType(row.user_feedback.error_type)" size="small" effect="light">
              {{ errorLabel(row.user_feedback.error_type) }}
            </el-tag>
            <span v-else style="color:#c0c4cc;">未分类</span>
          </template>
        </el-table-column>
        <el-table-column label="配置" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.config_name" size="small">{{ row.config_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="有纠正答案" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.user_feedback?.correct_answer" size="small" type="success">✓</el-tag>
            <span v-else style="color:#c0c4cc;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="140">
          <template #default="{ row }">
            {{ (row.timestamp ?? '').slice(0, 16).replace('T', ' ') }}
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="badTotal > pageSize"
        :total="badTotal"
        :page-size="pageSize"
        :current-page="page"
        layout="prev,pager,next,total"
        style="margin-top:12px; justify-content:flex-end; display:flex;"
        @current-change="(p: number) => { page = p; fetchBadCases() }"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Refresh, Download, Plus, Warning, TrendCharts, DocumentChecked } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

const stats = ref({ total: 0, good: 0, bad: 0, good_rate: 0 })
const analysis = ref<any>({})
const badCases = ref<any[]>([])
const badTotal = ref(0)
const keyword = ref('')
const filterErrorType = ref('')
const filterConfig = ref('')
const page = ref(1)
const pageSize = 20
const addingToEval = ref(false)

onMounted(fetchAll)

async function fetchAll() {
  await Promise.all([fetchStats(), fetchAnalysis(), fetchBadCases()])
}

async function fetchStats() {
  try { const r = await http.get('/monitor/stats'); stats.value = r.data } catch { /* ignore */ }
}

async function fetchAnalysis() {
  try { const r = await http.get('/monitor/error-analysis'); analysis.value = r.data } catch { /* ignore */ }
}

async function fetchBadCases() {
  try {
    const offset = (page.value - 1) * pageSize
    const r = await http.get('/monitor/bad-cases', {
      params: {
        limit: pageSize, offset,
        keyword: keyword.value || undefined,
        error_type: filterErrorType.value || undefined,
        config_name: filterConfig.value || undefined,
      },
    })
    badCases.value = r.data.items
    badTotal.value = r.data.total
  } catch { /* ignore */ }
}

async function exportBadCases() {
  const token = localStorage.getItem('token') ?? ''
  const resp = await fetch('/api/monitor/export', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'bad_cases.jsonl'; a.click()
  URL.revokeObjectURL(url)
}

async function addToEval() {
  addingToEval.value = true
  try {
    const token = localStorage.getItem('token') ?? ''
    const r = await fetch('/api/monitor/add-to-eval', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    const data = await r.json()
    ElMessage.success(data.message || `已加入 ${data.added} 条`)
  } catch {
    ElMessage.error('加入评测集失败')
  } finally {
    addingToEval.value = false
  }
}

// ---- 辅助函数 ----
function barPct(cnt: number | string, total: number): number {
  if (!total) return 0
  return Math.round((Number(cnt) / total) * 100)
}

function errorLabel(etype: string | number | undefined): string {
  const key = String(etype ?? '')
  const map: Record<string, string> = {
    hallucination: '幻觉',
    irrelevant: '不相关',
    incomplete: '不完整',
    factual_error: '事实错误',
    outdated: '过时',
    other: '其他',
    unclassified: '未分类',
  }
  return map[key] ?? key
}

function errorTagType(etype: string | number | undefined): '' | 'success' | 'warning' | 'danger' | 'info' {
  const key = String(etype ?? '')
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    hallucination: 'danger',
    irrelevant: 'warning',
    incomplete: 'warning',
    factual_error: 'danger',
    outdated: 'info',
    other: 'info',
    unclassified: 'info',
  }
  return map[key] ?? 'info'
}

function errorColor(etype: string | number | undefined): string {
  const key = String(etype ?? '')
  const map: Record<string, string> = {
    hallucination: '#f56c6c',
    irrelevant: '#e6a23c',
    incomplete: '#f5a623',
    factual_error: '#c0392b',
    outdated: '#909399',
    other: '#b0b3b8',
    unclassified: '#c0c4cc',
  }
  return map[key] ?? '#c0c4cc'
}

function errorStage(etype: string | number | undefined): string {
  const key = String(etype ?? '')
  const map: Record<string, string> = {
    hallucination: 'generate',
    irrelevant: 'retrieval',
    incomplete: 'retrieval+generate',
    factual_error: 'retrieval+generate',
    outdated: 'index',
  }
  return map[key] ?? 'unknown'
}

function stageLabel(stage: string | number | undefined): string {
  const key = String(stage ?? '')
  const map: Record<string, string> = {
    generate: '生成阶段',
    retrieval: '检索阶段',
    'retrieval+generate': '检索+生成',
    index: '索引阶段',
    unknown: '未知',
  }
  return map[key] ?? key
}

function optimizationHint(etype: string | number | undefined): string {
  const key = String(etype ?? '')
  const map: Record<string, string> = {
    hallucination: '建议：调低 temperature，增加引用约束提示词，使用更严格的 Grounding 检查',
    irrelevant: '建议：优化检索策略（增大 top_k、调整 hybrid_alpha），检查向量模型效果',
    incomplete: '建议：增大 top_k 或启用父子块检索，确保关键段落被召回',
    factual_error: '建议：检查文档质量，考虑重建索引；使用重排序过滤低相关块',
    outdated: '建议：更新知识库文档，定期重新索引',
    other: '建议：人工分析具体原因，针对性优化',
  }
  return map[key] ?? '建议：人工分析问题原因'
}

function rateColor(rate: number): string {
  if (rate >= 80) return '#67c23a'
  if (rate >= 60) return '#409eff'
  if (rate >= 40) return '#e6a23c'
  return '#f56c6c'
}

const byConfigRows = computed(() => {
  if (!analysis.value?.by_config) return []
  return Object.entries(analysis.value.by_config).map(([name, v]: [string, any]) => ({
    name, total: v.total, helpful: v.helpful, good_rate: v.good_rate,
  }))
})

const suggestions = computed(() => {
  const result: any[] = []
  const et = analysis.value?.error_types ?? {}
  const total = analysis.value?.total_bad ?? 0
  if (!total) return result

  if ((et.hallucination ?? 0) / total > 0.3) {
    result.push({
      title: '幻觉问题突出（>30% Bad Case）',
      desc: '调低 temperature，在 Prompt 中强调"只根据上下文回答"，禁止模型猜测',
      color: '#f56c6c', icon: Warning,
    })
  }
  if ((et.irrelevant ?? 0) / total > 0.2) {
    result.push({
      title: '检索相关性不足（>20% Bad Case）',
      desc: '尝试切换到 precision 或 full 配置，开启重排序和父子块检索',
      color: '#e6a23c', icon: TrendCharts,
    })
  }
  if ((et.incomplete ?? 0) / total > 0.2) {
    result.push({
      title: '答案不完整（>20% Bad Case）',
      desc: '增大 retrieval top_k，启用父子块扩展，或调整 chunk_size 使切分更细',
      color: '#e6a23c', icon: DocumentChecked,
    })
  }
  if ((et.factual_error ?? 0) / total > 0.15) {
    result.push({
      title: '事实错误率高（>15% Bad Case）',
      desc: '检查文档解析质量，对 PDF 表格/数字密集段落建议使用 OCR 或结构化提取',
      color: '#f56c6c', icon: Warning,
    })
  }

  // 配置对比建议
  const byConfig = analysis.value?.by_config ?? {}
  const configEntries = Object.entries(byConfig) as [string, any][]
  if (configEntries.length >= 2) {
    const sorted = configEntries.sort((a, b) => b[1].good_rate - a[1].good_rate)
    const best = sorted[0]
    if (best) {
      result.push({
        title: `配置 ${best[0].toUpperCase()} 好评率最高（${best[1].good_rate}%）`,
        desc: `当前各配置中 ${best[0]} 效果最好，建议将默认配置切换到 ${best[0]}`,
        color: '#67c23a', icon: TrendCharts,
      })
    }
  }

  return result
})
</script>

<style scoped>
.page-container { padding: 24px; height: 100%; overflow-y: auto; box-sizing: border-box; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-header h2 { margin: 0; }

.error-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.error-info {
  width: 160px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
}
.error-bar-wrap {
  flex: 1;
  height: 8px;
  background: #f0f2f5;
  border-radius: 4px;
  overflow: hidden;
}
.error-bar {
  height: 100%;
  border-radius: 4px;
  transition: width .4s ease;
}
.error-count {
  width: 28px;
  text-align: right;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  flex-shrink: 0;
}

.suggestion-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  background: #f8f9fa;
  margin-bottom: 8px;
}
.suggestion-row .el-icon {
  margin-top: 2px;
  flex-shrink: 0;
  font-size: 16px;
}
</style>
