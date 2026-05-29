<template>
  <el-drawer
    v-model="visible"
    title="⚙️ 检索配置"
    direction="rtl"
    size="440px"
    :destroy-on-close="false"
  >
    <div class="config-drawer">
      <div class="section-title">📋 当前预设：<el-tag>{{ configName.toUpperCase() }}</el-tag></div>

      <!-- ① 核心参数 -->
      <div class="section-title">🔢 核心参数</div>
      <el-form label-position="top" size="small">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item>
              <template #label>
                文本块大小
                <el-tooltip content="每个文本块包含的字符数，影响语义完整性">
                  <el-icon style="margin-left:4px; cursor:help;"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-slider v-model="form.chunk_size" :min="100" :max="1500" :step="50"
                show-input :input-size="'small'" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item>
              <template #label>
                召回数量 top_k
                <el-tooltip content="从向量库召回的候选文档数，越大覆盖越广但越慢">
                  <el-icon style="margin-left:4px; cursor:help;"><QuestionFilled /></el-icon>
                </el-tooltip>
              </template>
              <el-slider v-model="form.top_k_retrieval" :min="5" :max="50" :step="5"
                show-input :input-size="'small'" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- ② 功能开关 -->
        <div class="section-title">⚡ 功能开关</div>
        <div class="toggle-grid">
          <div class="toggle-item">
            <el-switch v-model="form.enable_parent_retrieval" />
            <div>
              <div class="toggle-label">📎 父子块</div>
              <div class="toggle-desc">关联父级大块内容，提升上下文完整性</div>
            </div>
          </div>
          <div class="toggle-item">
            <el-switch v-model="form.enable_history" />
            <div>
              <div class="toggle-label">💬 对话历史</div>
              <div class="toggle-desc">支持多轮对话，记忆上下文</div>
            </div>
          </div>
          <div class="toggle-item">
            <el-switch v-model="form.enable_multiquery" />
            <div>
              <div class="toggle-label">🔄 MultiQuery 扩展</div>
              <div class="toggle-desc">生成多个查询变体，扩大召回面</div>
            </div>
          </div>
          <div class="toggle-item">
            <el-switch v-model="form.enable_query_rewrite" />
            <div>
              <div class="toggle-label">✏️ Query 改写</div>
              <div class="toggle-desc">智能改写查询，匹配文档表述</div>
            </div>
          </div>
          <div class="toggle-item">
            <el-switch v-model="form.enable_rerank" />
            <div>
              <div class="toggle-label">🗳️ 重排（Rerank）</div>
              <div class="toggle-desc">LLM 二次精排，提升结果相关性</div>
            </div>
          </div>
        </div>

        <!-- ③ 重排设置（仅开启重排时显示） -->
        <template v-if="form.enable_rerank">
          <div class="section-title">🎯 重排设置</div>
          <el-row :gutter="16">
            <el-col :span="14">
              <el-form-item label="精排返回数量 rerank_top_k">
                <el-slider v-model="form.rerank_top_k" :min="3" :max="20" :step="1"
                  show-input :input-size="'small'" />
              </el-form-item>
            </el-col>
            <el-col :span="10">
              <el-form-item label="Jina Reranker">
                <div class="toggle-item" style="margin-top:4px;">
                  <el-switch v-model="form.use_jina_reranker" />
                  <span style="font-size:12px; color:#606266; margin-left:6px;">
                    {{ form.use_jina_reranker ? 'Jina API' : 'LLM 重排' }}
                  </span>
                </div>
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <!-- ④ 融合策略 -->
        <div class="section-title">⚖️ 融合策略</div>
        <el-form-item label="融合算法">
          <el-radio-group v-model="form.fusion_method">
            <el-radio-button value="rrf">RRF（推荐，基于排名）</el-radio-button>
            <el-radio-button value="weighted">加权（基于分数）</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.fusion_method === 'weighted'">
          <el-form-item label="BM25 关键词权重">
            <el-slider v-model="form.bm25_weight" :min="0" :max="1" :step="0.05"
              show-input :input-size="'small'" />
          </el-form-item>
          <div class="weight-visual">
            <div class="weight-bar">
              <div class="weight-fill bm25"
                :style="{ width: (form.bm25_weight * 100) + '%' }" />
              <div class="weight-fill vector"
                :style="{ width: ((1 - form.bm25_weight) * 100) + '%' }" />
            </div>
            <div class="weight-labels">
              <span>关键词 {{ Math.round(form.bm25_weight * 100) }}%</span>
              <span>语义 {{ Math.round((1 - form.bm25_weight) * 100) }}%</span>
            </div>
          </div>
        </template>

        <template v-if="form.fusion_method === 'rrf'">
          <el-form-item>
            <template #label>
              RRF 平滑参数 k
              <el-tooltip content="k 越大，排名差异越平缓；默认 60">
                <el-icon style="margin-left:4px; cursor:help;"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-slider v-model="form.rrf_k" :min="10" :max="200" :step="10"
              show-input :input-size="'small'" />
          </el-form-item>
        </template>
      </el-form>

      <!-- 变更对比 -->
      <div v-if="changedKeys.length > 0" class="diff-section">
        <div style="font-size:12px; font-weight:600; color:#303133; margin-bottom:6px;">
          📝 与预设差异（{{ changedKeys.length }} 项）
        </div>
        <div v-for="key in changedKeys" :key="key" class="diff-row">
          <span class="diff-key">{{ key }}</span>
          <span class="diff-old">{{ defaultVal(key) }}</span>
          <el-icon><Right /></el-icon>
          <span class="diff-new">{{ (form as any)[key] }}</span>
        </div>
      </div>
    </div>

    <!-- 底部按钮 -->
    <template #footer>
      <div style="display:flex; gap:8px;">
        <el-button type="primary" @click="handleSave" style="flex:1;">✅ 保存生效</el-button>
        <el-button @click="handleReset">🔄 恢复预设</el-button>
        <el-button @click="visible = false">关闭</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled, Right } from '@element-plus/icons-vue'
import { useConfigStore, type RetrievalOverrides } from '@/stores/config'

const props = defineProps<{ modelValue: boolean; configName: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const configStore = useConfigStore()

// 表单数据（合并默认值 + 当前覆盖）
const form = ref<Required<RetrievalOverrides>>({
  chunk_size: 500,
  chunk_overlap: 150,
  top_k_retrieval: 20,
  enable_parent_retrieval: true,
  enable_history: true,
  enable_multiquery: true,
  enable_query_rewrite: true,
  enable_rerank: true,
  rerank_top_k: 5,
  use_jina_reranker: false,
  fusion_method: 'rrf',
  bm25_weight: 0.3,
  rrf_k: 60,
})

// 打开时从 store 加载当前生效参数
watch(() => props.modelValue, (open) => {
  if (open) loadForm()
})

watch(() => props.configName, () => {
  if (props.modelValue) loadForm()
})

function loadForm() {
  const effective = configStore.getEffective(props.configName)
  Object.assign(form.value, effective)
}

/** 与预设默认值的差异 */
const changedKeys = computed(() => {
  const defaults = configStore.presetDefaults[props.configName] ?? {}
  return Object.keys(form.value).filter((k) => {
    const key = k as keyof RetrievalOverrides
    const def = (defaults as any)[key]
    const cur = (form.value as any)[key]
    return def !== undefined && def !== cur
  })
})

function defaultVal(key: string) {
  return (configStore.presetDefaults[props.configName] as any)?.[key] ?? '-'
}

function handleSave() {
  configStore.setOverrides(props.configName, { ...form.value })
  ElMessage.success('配置已保存，下次提问时生效')
  visible.value = false
}

function handleReset() {
  configStore.resetOverrides(props.configName)
  loadForm()
  ElMessage.info('已恢复预设默认值')
}
</script>

<style scoped>
.config-drawer {
  padding: 0 4px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin: 16px 0 10px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}

.toggle-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.toggle-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toggle-label {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.toggle-desc {
  font-size: 11px;
  color: #909399;
  margin-top: 1px;
}

.weight-visual {
  margin: -8px 0 12px;
}

.weight-bar {
  display: flex;
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
  background: #f0f2f5;
}

.weight-fill {
  height: 100%;
  transition: width .3s ease;
}

.weight-fill.bm25 { background: #409eff; }
.weight-fill.vector { background: #67c23a; }

.weight-labels {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #909399;
  margin-top: 3px;
}

.diff-section {
  background: #f8f9fa;
  border-radius: 6px;
  padding: 10px 12px;
  margin-top: 12px;
  border: 1px solid #ebeef5;
}

.diff-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  margin-bottom: 4px;
  color: #606266;
}

.diff-key {
  width: 160px;
  font-weight: 500;
  color: #303133;
  flex-shrink: 0;
}

.diff-old {
  color: #f56c6c;
  text-decoration: line-through;
}

.diff-new {
  color: #67c23a;
  font-weight: 600;
}
</style>
