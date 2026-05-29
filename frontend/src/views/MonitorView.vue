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
      <!-- 错误类型分析（M3：含可展开诊断） -->
      <el-col :span="14">
        <el-card style="height:100%;">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between;">
              <span>🔍 错误类型分布 &amp; 诊断</span>
              <el-tag size="small" type="danger" effect="plain">
                Bad Case 共 {{ analysis.total_bad ?? 0 }} 条
              </el-tag>
            </div>
          </template>

          <el-empty v-if="!analysis.error_types || !Object.keys(analysis.error_types).length"
            description="暂无 Bad Case 数据" :image-size="60" />

          <el-collapse v-else accordion>
            <el-collapse-item v-for="(cnt, etype) in analysis.error_types" :key="etype" :name="etype">
              <template #title>
                <div class="error-row" style="flex:1; margin-bottom:0;">
                  <div class="error-info">
                    <el-tag :type="errorTagType(etype)" size="small" effect="light">
                      {{ errorLabel(etype) }}
                    </el-tag>
                    <span style="font-size:11px; color:#909399; margin-left:6px;">
                      {{ stageLabel(errorStage(etype)) }}
                    </span>
                  </div>
                  <div class="error-bar-wrap">
                    <div class="error-bar"
                      :style="{ width: barPct(cnt, analysis.total_bad) + '%', background: errorColor(etype) }" />
                  </div>
                  <span class="error-count">{{ cnt }}</span>
                </div>
              </template>

              <!-- M3: 展开诊断面板 -->
              <div v-if="getDiagnosis(etype)" class="diagnosis-panel">
                <el-row :gutter="12">
                  <el-col :span="12">
                    <div class="diag-block">
                      <div class="diag-title">🔎 根因分析</div>
                      <div class="diag-text">{{ getDiagnosis(etype)!.root_cause }}</div>
                    </div>
                    <div class="diag-block" style="margin-top:8px;">
                      <div class="diag-title">📋 诊断说明</div>
                      <div class="diag-text">{{ getDiagnosis(etype)!.diagnosis }}</div>
                    </div>
                  </el-col>
                  <el-col :span="12">
                    <div class="diag-block">
                      <div class="diag-title">⚙️ 调参建议</div>
                      <ul class="diag-list">
                        <li v-for="(p, pi) in getDiagnosis(etype)!.optimize_params" :key="pi">{{ p }}</li>
                      </ul>
                    </div>
                    <div class="diag-block" style="margin-top:8px;">
                      <div class="diag-title">✅ 验证方法</div>
                      <div class="diag-text tip">{{ getDiagnosis(etype)!.eval_tip }}</div>
                    </div>
                  </el-col>
                </el-row>

                <!-- 示例问题 -->
                <div v-if="analysis.error_queries?.[etype]?.length" style="margin-top:8px;">
                  <div class="diag-title">💬 示例问题</div>
                  <ul class="diag-list">
                    <li v-for="(q, qi) in analysis.error_queries[etype]" :key="qi">{{ q }}</li>
                  </ul>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-col>

      <!-- 阶段分布 & 配置对比 -->
      <el-col :span="10">
        <el-card style="margin-bottom:12px;">
          <template #header><span>⚙️ Pipeline 阶段分布</span></template>
          <el-empty v-if="!analysis.stage_distribution || !Object.keys(analysis.stage_distribution).length"
            description="暂无数据" :image-size="60" />
          <div v-else>
            <div v-for="(cnt, stage) in analysis.stage_distribution" :key="stage" class="error-row">
              <el-tag size="small" effect="plain" :type="stageTagType(stage)">{{ stageLabel(stage) }}</el-tag>
              <div class="error-bar-wrap">
                <div class="error-bar"
                  :style="{ width: barPct(cnt, analysis.total_bad) + '%', background: stageColor(stage) }" />
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
            <el-table-column label="总数" prop="total" width="60" align="center" />
            <el-table-column label="好评" prop="helpful" width="60" align="center" />
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

    <!-- M7: 优化路线图 -->
    <el-card v-if="roadmapItems.length > 0" style="margin-bottom:20px;">
      <template #header>
        <span>🗺️ 优化路线图</span>
        <el-tooltip content="根据 Bad Case 分布自动生成的分阶段优先优化建议">
          <el-icon style="margin-left:6px; color:#909399; cursor:help;"><QuestionFilled /></el-icon>
        </el-tooltip>
      </template>
      <el-steps :active="0" direction="vertical" style="padding:8px 0;">
        <el-step v-for="(item, idx) in roadmapItems" :key="idx"
          :title="item.title"
          :description="item.desc"
          :status="item.status"
          :icon="item.icon">
        </el-step>
      </el-steps>
    </el-card>

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
                <!-- 左列：问答内容 -->
                <el-col :span="12">
                  <div style="font-weight:600; color:#303133; margin-bottom:4px;">问题</div>
                  <div style="color:#606266;">{{ row.query }}</div>
                  <div style="font-weight:600; color:#303133; margin-top:10px; margin-bottom:4px;">答案</div>
                  <div style="color:#606266; white-space:pre-wrap;">{{ row.answer }}</div>
                </el-col>
                <!-- 右列：用户反馈 + M5-M6 Pipeline 诊断 -->
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

                  <!-- M5-M6: Pipeline 诊断 -->
                  <div class="pipeline-diag" style="margin-top:12px;">
                    <div style="font-weight:600; color:#303133; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
                      🔬 Pipeline 诊断
                      <el-tag size="small" :type="stageTagType(errorStage(row.user_feedback?.error_type))" effect="light">
                        {{ stageLabel(errorStage(row.user_feedback?.error_type)) }}
                      </el-tag>
                    </div>
                    <div v-if="getDiagnosis(row.user_feedback?.error_type)" class="diag-mini">
                      <div class="diag-mini-row">
                        <span class="diag-mini-label">根因</span>
                        <span>{{ getDiagnosis(row.user_feedback?.error_type)!.root_cause }}</span>
                      </div>
                      <div class="diag-mini-row" style="margin-top:6px;">
                        <span class="diag-mini-label">修复</span>
                        <ul style="margin:0; padding-left:14px; color:#606266;">
                          <li v-for="(p, pi) in getDiagnosis(row.user_feedback?.error_type)!.optimize_params" :key="pi"
                            style="font-size:12px;">{{ p }}</li>
                        </ul>
                      </div>
                      <div class="diag-mini-row" style="margin-top:6px;">
                        <span class="diag-mini-label">验证</span>
                        <span style="color:#409eff; font-size:12px;">
                          {{ getDiagnosis(row.user_feedback?.error_type)!.eval_tip }}
                        </span>
                      </div>
                    </div>
                    <div v-else style="font-size:12px; color:#909399;">
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
        <el-table-column label="阶段" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain"
              :type="stageTagType(errorStage(row.user_feedback?.error_type))">
              {{ stageLabel(errorStage(row.user_feedback?.error_type)) }}
            </el-tag>
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
import { Refresh, Download, Plus, Warning, TrendCharts, DocumentChecked, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/api/http'

// ---- 错误诊断知识库 (M3) ----
interface DiagnosisEntry {
  root_cause: string
  diagnosis: string
  optimize_params: string[]
  eval_tip: string
}

const ERROR_DIAGNOSIS: Record<string, DiagnosisEntry> = {
  hallucination: {
    root_cause: 'LLM 在上下文不足时进行了推测性生成，超出了检索结果范围',
    diagnosis: '答案包含检索文档中不存在的信息。通常发生在检索召回不足或 prompt 约束力弱的情况下。',
    optimize_params: [
      '降低 LLM temperature（建议 0.1~0.3）',
      '在 prompt 中加入"仅根据以下上下文回答，不确定时说不知道"',
      '增大 top_k_retrieval 确保更多上下文可用',
      '启用 Rerank 过滤低相关性块',
    ],
    eval_tip: '运行评估并关注 Faithfulness 指标；使用 LLM-as-Judge 模式检测答案是否有据可查',
  },
  irrelevant: {
    root_cause: '向量检索召回了主题偏离的文档，或 Query 与文档表述不匹配',
    diagnosis: '答案与问题无关，说明检索阶段未找到正确文档。可能是向量模型语义理解不足或 Query 未经改写。',
    optimize_params: [
      '启用 Query 改写（enable_query_rewrite=true）',
      '启用 MultiQuery 扩大召回面（enable_multiquery=true）',
      '增大 top_k_retrieval（建议 ≥20）',
      '检查 BM25 权重配置，考虑混合检索比例',
    ],
    eval_tip: '运行评估关注 Hit@5 和 Recall@5；如低于 0.7 说明检索阶段问题显著',
  },
  incomplete: {
    root_cause: '相关文档被召回但不完整，或关键信息分散在多个 Chunk 中未被合并',
    diagnosis: '答案遗漏了关键信息，通常是 chunk 切分过细或 top_k 不够大，导致覆盖不全。',
    optimize_params: [
      '启用父子块检索（enable_parent_retrieval=true）',
      '增大 chunk_size（建议 500~800）',
      '增大 top_k_retrieval（建议 ≥20）',
      '增大 rerank_top_k 保留更多候选块',
    ],
    eval_tip: '运行评估关注 Recall@5 和 NDCG@5；比较启用/关闭父子块的差异',
  },
  factual_error: {
    root_cause: '文档中的事实信息被错误理解，或 LLM 在多个片段混合时出现数字/日期混淆',
    diagnosis: '答案包含错误的数字、日期或事实。通常源于检索结果质量低或文档解析错误（表格、图表）。',
    optimize_params: [
      '检查文档解析质量，特别是表格和数字密集段落',
      '重建索引（重新 chunk 文档）',
      '启用 Rerank 提升相关文档排名',
      '在 prompt 中强调引用具体数字时要原文引用',
    ],
    eval_tip: '人工核查高频错误问题；对比不同 chunk_size 下的评估分数',
  },
  outdated: {
    root_cause: '知识库中的文档版本过旧，与用户问题所需信息存在时效差距',
    diagnosis: '答案引用了过期信息。知识库需要更新以包含最新文档版本。',
    optimize_params: [
      '更新知识库文档（上传新版 PDF）',
      '重新执行文档解析和索引构建',
      '在文档元数据中记录版本/时间信息',
    ],
    eval_tip: '更新文档后重新运行评估，对比新旧指标变化',
  },
  other: {
    root_cause: '问题原因未明确分类，需要人工分析具体场景',
    diagnosis: '该 Bad Case 标记为"其他"类型，建议人工查看问题细节，寻找共性模式后归类。',
    optimize_params: [
      '人工阅读问题和答案，识别问题模式',
      '考虑将其细化为上述具体错误类型',
      '收集更多同类问题后针对性优化',
    ],
    eval_tip: '聚焦评估集中的相似问题，观察系统性偏差',
  },
  unclassified: {
    root_cause: '用户未为该 Bad Case 指定错误类型',
    diagnosis: '未分类的 Bad Case 可能隐含各类问题。建议在差评时引导用户选择错误类型。',
    optimize_params: [
      '在差评弹窗中设置必填的错误类型字段',
      '定期人工分类未标注的 Bad Case',
    ],
    eval_tip: '提高 Bad Case 分类率，有助于更精准的问题定位',
  },
}

function getDiagnosis(etype: string | number | undefined): DiagnosisEntry | null {
  return ERROR_DIAGNOSIS[String(etype ?? '')] ?? null
}

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

function stageTagType(stage: string | number | undefined): '' | 'success' | 'warning' | 'danger' | 'info' {
  const key = String(stage ?? '')
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    generate: 'danger',
    retrieval: 'warning',
    'retrieval+generate': 'warning',
    index: 'info',
    unknown: 'info',
  }
  return map[key] ?? 'info'
}

function stageColor(stage: string | number | undefined): string {
  const key = String(stage ?? '')
  const map: Record<string, string> = {
    generate: '#f56c6c',
    retrieval: '#e6a23c',
    'retrieval+generate': '#f5a623',
    index: '#909399',
    unknown: '#c0c4cc',
  }
  return map[key] ?? '#c0c4cc'
}

function optimizationHint(etype: string | number | undefined): string {
  const d = getDiagnosis(etype)
  if (d) return d.optimize_params[0] ?? ''
  return '建议：人工分析问题原因'
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

// M7: 优化路线图 — 按阶段优先级生成步骤
const roadmapItems = computed(() => {
  const et = analysis.value?.error_types ?? {}
  const total = analysis.value?.total_bad ?? 0
  if (!total) return []

  const items: any[] = []

  // 索引阶段
  const indexCnt = et.outdated ?? 0
  if (indexCnt > 0) {
    items.push({
      title: `【索引阶段】更新知识库文档（${indexCnt} 条过时问题）`,
      desc: '上传最新版 PDF 并重新执行文档解析与分块索引',
      status: indexCnt / total > 0.2 ? 'error' : 'process',
      icon: null,
    })
  }

  // 检索阶段
  const retrievalCnt = (et.irrelevant ?? 0) + (et.incomplete ?? 0)
  if (retrievalCnt > 0) {
    const pct = Math.round(retrievalCnt / total * 100)
    items.push({
      title: `【检索阶段】优化召回策略（${retrievalCnt} 条相关性/完整性问题，占 ${pct}%）`,
      desc: '启用 Query 改写 + MultiQuery + 父子块检索；增大 top_k；调整 BM25/RRF 融合权重',
      status: pct > 30 ? 'error' : 'process',
      icon: null,
    })
  }

  // 重排阶段
  const factCnt = et.factual_error ?? 0
  if (factCnt > 0) {
    items.push({
      title: `【重排阶段】提升精排质量（${factCnt} 条事实错误）`,
      desc: '启用 Rerank 精排过滤低相关块；调整 rerank_top_k；检查文档解析质量',
      status: factCnt / total > 0.15 ? 'error' : 'process',
      icon: null,
    })
  }

  // 生成阶段
  const hallCnt = et.hallucination ?? 0
  if (hallCnt > 0) {
    const pct = Math.round(hallCnt / total * 100)
    items.push({
      title: `【生成阶段】控制幻觉输出（${hallCnt} 条幻觉问题，占 ${pct}%）`,
      desc: '降低 temperature，强化 Grounding Prompt，限制模型只基于上下文回答',
      status: pct > 30 ? 'error' : 'process',
      icon: null,
    })
  }

  // 验证阶段（始终显示）
  items.push({
    title: '【验证阶段】重新运行评估集，对比优化前后指标',
    desc: '在评估测试页运行多配置对比，关注 Hit@5 / Recall@5 / MRR 变化趋势',
    status: 'wait',
    icon: null,
  })

  return items
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

/* M3 诊断面板 */
.diagnosis-panel {
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
  margin-top: 4px;
  border: 1px solid #ebeef5;
  font-size: 12px;
}

.diag-block {
  background: #fff;
  border-radius: 4px;
  padding: 8px 10px;
  border: 1px solid #f0f0f0;
}

.diag-title {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.diag-text {
  color: #606266;
  line-height: 1.6;
}

.diag-text.tip {
  color: #409eff;
}

.diag-list {
  margin: 0;
  padding-left: 16px;
  color: #606266;
  line-height: 1.8;
}

/* M5-M6 Pipeline 诊断（Bad Case 展开中） */
.pipeline-diag {
  background: #f8f9fa;
  border-radius: 6px;
  padding: 10px 12px;
  border: 1px solid #ebeef5;
}

.diag-mini {
  font-size: 12px;
}

.diag-mini-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.diag-mini-label {
  background: #409eff;
  color: #fff;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  flex-shrink: 0;
  line-height: 18px;
}
</style>
