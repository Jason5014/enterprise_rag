<template>
  <div class="page-container">
    <div class="page-header">
      <h2>📊 评估测试</h2>
    </div>

    <!-- ===== 配置区 ===== -->
    <el-card style="margin-bottom:16px;">
      <el-row :gutter="16" align="middle">
        <el-col :span="5">
          <el-form-item label="知识库" style="margin-bottom:0;">
            <el-select v-model="form.kb_id" placeholder="默认内置" clearable style="width:100%;">
              <el-option v-for="kb in kbList" :key="kb.kb_id" :label="kb.name" :value="kb.kb_id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="4">
          <el-form-item label="场景分类" style="margin-bottom:0;">
            <el-select v-model="form.category_filter" style="width:100%;">
              <el-option label="全部" value="" />
              <el-option v-for="(desc, cat) in evalInfo?.categories" :key="cat"
                :label="`${cat} - ${desc}`" :value="cat" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="评估模式" style="margin-bottom:0;">
            <el-radio-group v-model="evalMode" size="small">
              <el-radio-button value="single">单配置</el-radio-button>
              <el-radio-button value="compare">多配置对比</el-radio-button>
              <el-radio-button value="variant">自定义变体</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :span="4">
          <el-checkbox v-model="form.enable_llm_eval">
            LLM-as-Judge
            <el-tooltip content="启用后评估 Faithfulness / Relevance / Completeness，会增加 API 调用">
              <el-icon style="cursor:help;"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-checkbox>
        </el-col>
        <el-col :span="5" style="text-align:right;">
          <el-button type="primary" :loading="running" @click="startEval" :icon="VideoPlay">
            {{ running ? '评估中...' : '开始评估' }}
          </el-button>
        </el-col>
      </el-row>

      <!-- 单配置模式 -->
      <template v-if="evalMode === 'single'">
        <el-divider style="margin:12px 0 8px;" />
        <el-form-item label="配置预设" style="margin-bottom:0;">
          <el-select v-model="form.config_name" style="width:200px;">
            <el-option label="BASE（基础）" value="base" />
            <el-option label="FAST（快速）" value="fast" />
            <el-option label="PRECISION（高精度）" value="precision" />
            <el-option label="FULL（完整）" value="full" />
          </el-select>
          <el-tag v-if="hasOverrides(form.config_name)" type="warning" size="small" style="margin-left:8px;">
            含自定义参数
          </el-tag>
        </el-form-item>
      </template>

      <!-- 多配置对比 -->
      <template v-if="evalMode === 'compare'">
        <el-divider style="margin:12px 0 8px;" />
        <el-form-item label="选择配置（至少2个）" style="margin-bottom:0;">
          <el-checkbox-group v-model="compareConfigs">
            <el-checkbox-button value="base">BASE</el-checkbox-button>
            <el-checkbox-button value="fast">FAST</el-checkbox-button>
            <el-checkbox-button value="precision">PRECISION</el-checkbox-button>
            <el-checkbox-button value="full">FULL</el-checkbox-button>
          </el-checkbox-group>
        </el-form-item>
      </template>

      <!-- 自定义变体 -->
      <template v-if="evalMode === 'variant'">
        <el-divider style="margin:12px 0 8px;" />
        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
          <span style="font-size:13px; color:#606266;">变体列表（{{ variants.length }}个）：</span>
          <el-tag v-for="(v, i) in variants" :key="i" closable @close="variants.splice(i, 1)" type="primary">
            {{ v.display_name }}
          </el-tag>
          <el-button size="small" :icon="Plus" @click="variantDialogOpen = true">添加变体</el-button>
        </div>
      </template>

      <!-- 测试集信息 -->
      <div v-if="evalInfo" style="margin-top:10px; font-size:12px; color:#909399; display:flex; align-items:center; gap:12px;">
        <span>📝 测试集：<strong>{{ evalInfo.total }}</strong> 题</span>
        <el-tag v-if="evalInfo.has_ground_truth" size="small" type="success" effect="plain">含 Ground Truth</el-tag>
        <el-tag v-else size="small" type="info" effect="plain">无 Ground Truth</el-tag>
        <span v-if="form.category_filter" style="color:#409eff;">
          已筛选场景：{{ form.category_filter }}
        </span>
      </div>

      <!-- 进度 -->
      <div v-if="running || progressMsg" style="margin-top:12px;">
        <el-progress :percentage="progress" :status="progressStatus" style="margin-bottom:4px;" />
        <div style="font-size:12px; color:#909399;">{{ progressMsg }}</div>
      </div>
    </el-card>

    <!-- ===== 单配置结果 ===== -->
    <template v-if="singleResult && evalMode === 'single'">
      <!-- 综合得分 -->
      <el-card shadow="never" class="score-card" style="margin-bottom:16px;">
        <div class="score-layout">
          <!-- 大圆环 -->
          <div class="score-left">
            <ScoreRing :value="singleResult.composite_score" :max="100" :size="92" />
            <div class="score-subtitle">综合得分 / 100</div>
            <el-tag :type="scoreLevelType(singleResult.composite_score)" size="small" effect="plain"
              style="margin-top:4px;">
              {{ scoreLevel(singleResult.composite_score) }}
            </el-tag>
          </div>
          <div class="score-divider" />
          <!-- 各指标小环 -->
          <div class="score-metrics">
            <el-tooltip v-for="m in mainMetricCards(singleResult.metrics)" :key="m.key"
              :content="metricHelp(m.key)" placement="top">
              <div class="metric-cell">
                <ScoreRing :value="m.val" :size="54" :label="m.label" />
                <div class="metric-level">{{ metricEmoji(m.val, m.key) }}</div>
              </div>
            </el-tooltip>
            <!-- 延迟 -->
            <div class="metric-cell latency-cell">
              <div class="latency-val" :style="{ color: latencyColor(singleResult.avg_latency_ms) }">
                {{ Math.round(singleResult.avg_latency_ms) }}
              </div>
              <div class="metric-label">延迟 ms</div>
              <div class="metric-level">{{ latencyEmoji(singleResult.avg_latency_ms) }}</div>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 低分指标分析 -->
      <template v-for="m in mainMetricCards(singleResult.metrics)" :key="'analysis-' + m.key">
        <el-collapse v-if="metricNeedsAnalysis(m.val, m.key)"
          style="margin-bottom:8px; border-radius:6px; overflow:hidden;">
          <el-collapse-item :name="m.key">
            <template #title>
              <span style="font-size:13px;">
                🔍 <strong>{{ m.label }}</strong> 分析与优化建议
                <el-tag :type="metricLevelType(m.val, m.key)" size="small" style="margin-left:8px;">
                  {{ fmtPct(m.val) }}
                </el-tag>
              </span>
            </template>
            <el-row :gutter="16" style="padding:8px 0;">
              <el-col :span="12">
                <div style="font-weight:600; margin-bottom:8px; color:#303133;">可能原因</div>
                <ul style="margin:0; padding-left:16px; font-size:13px; color:#606266; line-height:1.8;">
                  <li v-for="r in metricInfo(m.key).low_reasons" :key="r">{{ r }}</li>
                </ul>
              </el-col>
              <el-col :span="12">
                <div style="font-weight:600; margin-bottom:8px; color:#303133;">优化方向</div>
                <ul style="margin:0; padding-left:16px; font-size:13px; color:#606266; line-height:1.8;">
                  <li v-for="t in metricInfo(m.key).optimize" :key="t">{{ t }}</li>
                </ul>
              </el-col>
            </el-row>
          </el-collapse-item>
        </el-collapse>
      </template>

      <!-- 按场景分类指标 -->
      <el-card v-if="singleResult.category_metrics && Object.keys(singleResult.category_metrics).length > 0"
        style="margin-bottom:16px;">
        <template #header>📊 按场景分类指标</template>
        <el-collapse>
          <el-collapse-item v-for="(scores, cat) in singleResult.category_metrics" :key="cat"
            :name="cat">
            <template #title>
              <span>
                [{{ cat }}]
                <span style="margin-left:8px; font-size:12px; color:#909399;">
                  {{ scores.count }} 题 ·
                  Hit@5 {{ fmtPct(scores['hit@5'] ?? 0) }} ·
                  Recall@5 {{ fmtPct(scores['recall@5'] ?? 0) }}
                </span>
              </span>
            </template>
            <div style="display:flex; flex-wrap:wrap; gap:12px; padding:10px 4px;">
              <div v-for="key in ['hit@5','recall@5','mrr','ndcg@5','recall@3','recall@1']" :key="key"
                class="metric-cell">
                <ScoreRing :value="scores[key] ?? 0" :size="50" :label="key.toUpperCase()" />
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </el-card>

      <!-- 逐题详情 -->
      <el-card style="margin-bottom:16px;">
        <template #header>
          <div style="display:flex; align-items:center; gap:12px;">
            <span>🔍 逐题检索详情</span>
            <el-tag size="small" type="info" effect="plain">
              命中率 {{ singleHitRate }}%（Top-5）
            </el-tag>
          </div>
        </template>
        <el-table :data="singleResult.results" stripe style="width:100%;">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div style="padding:12px 24px; background:#fafafa; font-size:13px; line-height:1.8;">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <div style="font-weight:600; margin-bottom:4px;">📌 预期 chunk（{{ row.relevant_chunks?.length ?? 0 }}个）</div>
                    <div v-for="ec in (row.relevant_chunks ?? [])" :key="ec" style="color:#67c23a; font-size:12px;">✅ {{ ec }}</div>
                    <div v-if="!row.relevant_chunks?.length" style="color:#c0c4cc; font-size:12px;">无 Ground Truth</div>
                  </el-col>
                  <el-col :span="12">
                    <div style="font-weight:600; margin-bottom:4px;">🔍 Top-10 检索结果</div>
                    <div v-for="(rid, j) in (row.retrieved_ids ?? []).slice(0, 10)" :key="j"
                      style="font-size:12px; display:flex; align-items:center; gap:6px; margin-bottom:2px;">
                      <span>{{ j === 0 ? '🥇' : j === 1 ? '🥈' : j === 2 ? '🥉' : `${j+1}.` }}</span>
                      <span :style="row.relevant_chunks?.includes(rid) ? 'color:#67c23a; font-weight:600;' : 'color:#909399;'">
                        {{ rid }}
                      </span>
                      <el-tag v-if="row.relevant_chunks?.includes(rid)" size="small" type="success" effect="plain">命中</el-tag>
                    </div>
                    <div v-if="missedChunks(row).length" style="margin-top:8px;">
                      <div style="font-weight:600; color:#f56c6c; font-size:12px; margin-bottom:2px;">
                        ❌ 未进入 Top-10（{{ missedChunks(row).length }}个）
                      </div>
                      <div v-for="mid in missedChunks(row)" :key="mid"
                        style="font-size:12px; color:#f56c6c;">{{ mid }}</div>
                    </div>
                  </el-col>
                </el-row>
              </div>
            </template>
          </el-table-column>
          <el-table-column type="index" width="50" />
          <el-table-column label="问题" prop="question" min-width="220" show-overflow-tooltip />
          <el-table-column label="类别" prop="category" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.category" size="small" effect="plain">{{ row.category }}</el-tag>
              <span v-else style="color:#c0c4cc;">-</span>
            </template>
          </el-table-column>
          <el-table-column label="命中" width="65" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_hit === true" size="small" type="success" effect="dark">✓</el-tag>
              <el-tag v-else-if="row.is_hit === false" size="small" type="danger" effect="dark">✗</el-tag>
              <span v-else style="color:#c0c4cc;">-</span>
            </template>
          </el-table-column>
          <el-table-column label="延迟(ms)" width="90" align="right">
            <template #default="{ row }">
              <span :style="{ color: latencyColor(row.latency_ms) }">{{ row.latency_ms }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="75" align="center">
            <template #default="{ row }">
              <el-tag :type="row.answer === 'ERROR' ? 'danger' : 'success'" size="small">
                {{ row.answer === 'ERROR' ? '失败' : '完成' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- ===== 多配置 / 变体对比结果 ===== -->
    <template v-if="compareResults.length > 0 && evalMode !== 'single'">
      <!-- 对比汇总表 -->
      <el-card style="margin-bottom:16px;">
        <template #header>
          <div style="display:flex; align-items:center; gap:12px;">
            <span>📊 配置对比汇总</span>
            <el-tag size="small" type="primary">{{ compareResults.length }} 个配置</el-tag>
          </div>
        </template>
        <el-table :data="compareTableRows" border style="width:100%;">
          <el-table-column label="配置" prop="name" width="140" fixed>
            <template #default="{ row }">
              <el-tag>{{ row.name }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="综合分" width="80" align="center">
            <template #default="{ row }">
              <span :style="{ color: scoreColor(row.score), fontWeight: 700 }">{{ row.score }}</span>
            </template>
          </el-table-column>
          <el-table-column v-for="key in compareMetricKeys" :key="key"
            :label="key.toUpperCase()" width="80" align="center">
            <template #default="{ row }">
              <span :style="{ color: metricColor(row.metrics[key] ?? 0, key) }">
                {{ fmtPct(row.metrics[key] ?? 0) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="延迟(ms)" width="90" align="right">
            <template #default="{ row }">
              <span :style="{ color: latencyColor(row.latency) }">{{ Math.round(row.latency) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 各项最佳 -->
        <div style="margin-top:12px; display:flex; flex-wrap:wrap; gap:8px;">
          <div v-for="item in bestItems" :key="item.key"
            style="background:#f0f9eb; border:1px solid #b3e19d; border-radius:6px; padding:6px 12px; font-size:12px;">
            🏆 <strong>{{ item.label }}</strong> 最佳：
            <el-tag type="success" size="small">{{ item.winner }}</el-tag>
            {{ item.value }}
          </div>
        </div>
      </el-card>

      <!-- 各配置逐题折叠 -->
      <el-card>
        <template #header>🔍 各配置检索详情</template>
        <el-collapse>
          <el-collapse-item v-for="r in compareResults" :key="r.config_name" :name="r.config_name">
            <template #title>
              <span>
                📋 {{ r.config_name.toUpperCase() }}
                <span style="font-size:12px; color:#909399; margin-left:8px;">
                  Hit@5 {{ fmtPct(r.metrics?.['hit@5'] ?? 0) }} · Recall@5 {{ fmtPct(r.metrics?.['recall@5'] ?? 0) }}
                </span>
              </span>
            </template>
            <el-table :data="r.results" size="small" stripe style="width:100%;">
              <el-table-column type="expand">
                <template #default="{ row }">
                  <div style="padding:10px 20px; background:#fafafa; font-size:12px;">
                    <div style="margin-bottom:6px; font-weight:600;">Top-10 检索结果</div>
                    <div v-for="(rid, j) in (row.retrieved_ids ?? []).slice(0,10)" :key="j"
                      style="display:flex; gap:6px; margin-bottom:2px;">
                      <span>{{ j===0?'🥇':j===1?'🥈':j===2?'🥉':`${j+1}.` }}</span>
                      <span :style="row.relevant_chunks?.includes(rid)?'color:#67c23a;font-weight:600;':'color:#909399;'">
                        {{ rid }}
                      </span>
                    </div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="问题" prop="question" min-width="200" show-overflow-tooltip />
              <el-table-column label="命中" width="60" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.is_hit===true" size="small" type="success" effect="dark">✓</el-tag>
                  <el-tag v-else-if="row.is_hit===false" size="small" type="danger" effect="dark">✗</el-tag>
                  <span v-else style="color:#c0c4cc;">-</span>
                </template>
              </el-table-column>
              <el-table-column label="延迟" width="80" align="right">
                <template #default="{ row }">
                  <span :style="{ color: latencyColor(row.latency_ms) }">{{ row.latency_ms }}</span>
                </template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </el-card>
    </template>

    <!-- ===== 评测历史 ===== -->
    <el-card style="margin-top:16px;">
      <template #header>
        <div style="display:flex; align-items:center;">
          <span>📈 评测历史</span>
          <el-button text :icon="Refresh" @click="fetchHistory" style="margin-left:auto;" />
        </div>
      </template>

      <!-- 趋势摘要 -->
      <div v-if="trendSummary" class="trend-summary">
        {{ trendSummary.arrow }} 最近两次：
        <strong>{{ trendSummary.prev_config }}（{{ trendSummary.prev_score }}分）</strong>
        →
        <strong>{{ trendSummary.cur_config }}（{{ trendSummary.cur_score }}分）</strong>
        <el-tag :type="trendSummary.diff >= 0 ? 'success' : 'danger'" size="small" style="margin-left:8px;">
          {{ trendSummary.diff >= 0 ? '+' : '' }}{{ trendSummary.diff }}
        </el-tag>
      </div>

      <el-empty v-if="history.length === 0" description="暂无历史记录" />

      <template v-else>
        <!-- 历史表格 -->
        <el-table :data="history" stripe style="width:100%;" size="small">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div style="padding:10px 24px; background:#fafafa;">
                <!-- 配置快照 -->
                <div v-if="row.config_snapshot" style="margin-bottom:8px;">
                  <span style="font-size:12px; font-weight:600; color:#303133;">配置参数：</span>
                  <span v-for="(v, k) in row.config_snapshot" :key="k" style="font-size:12px; color:#606266; margin-right:12px;">
                    <strong>{{ k }}</strong>: {{ v }}
                  </span>
                </div>
                <!-- 指标一览 -->
                <el-row :gutter="8">
                  <el-col :span="3" v-for="key in ['hit@1','hit@3','hit@5','recall@5','mrr','ndcg@5','faithfulness','completeness']" :key="key">
                    <div class="metric-cell" style="padding:4px;">
                      <div style="font-size:16px; font-weight:700;" :style="{ color: metricColor(row.metrics?.[key] ?? 0, key) }">
                        {{ fmtPct(row.metrics?.[key] ?? 0) }}
                      </div>
                      <div style="font-size:10px; color:#909399;">{{ key.toUpperCase() }}</div>
                    </div>
                  </el-col>
                </el-row>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="145">
            <template #default="{ row }">{{ (row.timestamp ?? '').slice(0,16).replace('T',' ') }}</template>
          </el-table-column>
          <el-table-column label="配置" prop="config_name" width="90">
            <template #default="{ row }"><el-tag size="small">{{ row.config_name }}</el-tag></template>
          </el-table-column>
          <el-table-column label="综合分" width="75" align="center">
            <template #default="{ row }">
              <span :style="{ color: scoreColor(row.composite_score ?? 0), fontWeight: 700 }">
                {{ Math.round(row.composite_score ?? 0) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="题数" prop="question_count" width="65" align="center" />
          <el-table-column label="Hit@1" width="70" align="center">
            <template #default="{ row }">{{ fmtHistPct(row.metrics?.['hit@1']) }}</template>
          </el-table-column>
          <el-table-column label="Hit@5" width="70" align="center">
            <template #default="{ row }">{{ fmtHistPct(row.metrics?.['hit@5']) }}</template>
          </el-table-column>
          <el-table-column label="Recall@5" width="78" align="center">
            <template #default="{ row }">{{ fmtHistPct(row.metrics?.['recall@5']) }}</template>
          </el-table-column>
          <el-table-column label="MRR" width="70" align="center">
            <template #default="{ row }">{{ fmtHistPct(row.metrics?.['mrr']) }}</template>
          </el-table-column>
          <el-table-column label="NDCG@5" width="78" align="center">
            <template #default="{ row }">{{ fmtHistPct(row.metrics?.['ndcg@5']) }}</template>
          </el-table-column>
          <el-table-column label="延迟(ms)" width="85" align="right">
            <template #default="{ row }">
              <span v-if="row.metrics?.avg_latency_ms">{{ Math.round(row.metrics.avg_latency_ms) }}</span>
              <span v-else style="color:#c0c4cc;">-</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <!-- ===== 添加变体弹窗 ===== -->
    <el-dialog v-model="variantDialogOpen" title="➕ 添加自定义变体" width="480px">
      <el-form :model="variantForm" label-position="top" size="small">
        <el-form-item label="基础预设">
          <el-select v-model="variantForm.config_name" style="width:100%;">
            <el-option label="BASE" value="base" />
            <el-option label="FAST" value="fast" />
            <el-option label="PRECISION" value="precision" />
            <el-option label="FULL" value="full" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="召回数量 top_k">
              <el-input-number v-model="variantForm.top_k_retrieval" :min="5" :max="50" style="width:100%;" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="重排数量 rerank_top_k">
              <el-input-number v-model="variantForm.rerank_top_k" :min="1" :max="20" style="width:100%;" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="MultiQuery 扩展">
              <el-switch v-model="variantForm.enable_multiquery" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Query 改写">
              <el-switch v-model="variantForm.enable_query_rewrite" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="Rerank 精排">
              <el-switch v-model="variantForm.enable_rerank" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Jina Reranker">
              <el-switch v-model="variantForm.use_jina_reranker" :disabled="!variantForm.enable_rerank" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="BM25 权重">
          <el-slider v-model="variantForm.bm25_weight" :min="0" :max="1" :step="0.05" show-input :input-size="'small'" />
        </el-form-item>
        <el-form-item label="变体名称（自动生成可修改）">
          <el-input v-model="variantForm.display_name" placeholder="自动生成" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="variantDialogOpen = false">取消</el-button>
        <el-button type="primary" @click="addVariant">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, defineComponent, h } from 'vue'
import { VideoPlay, Refresh, Plus, QuestionFilled } from '@element-plus/icons-vue'
import { kbApi } from '@/api/kb'
import { useConfigStore } from '@/stores/config'
import http from '@/api/http'

// ── ScoreRing：纯 SVG 圆环指标组件 ──
const ScoreRing = defineComponent({
  props: {
    value:  { type: Number, default: 0 },   // 0-1（指标）或 0-100（综合分）
    max:    { type: Number, default: 1 },    // 1=百分比模式，100=分数模式
    size:   { type: Number, default: 54 },
    color:  { type: String, default: '' },
    label:  { type: String, default: '' },
  },
  setup(props) {
    const r = 22; const cx = 28; const cy = 28
    const circ = 2 * Math.PI * r
    return () => {
      const pct    = props.max === 100 ? props.value / 100 : props.value
      const clamped = Math.min(1, Math.max(0, pct))
      const offset = circ * (1 - clamped)
      const dispVal = props.max === 100 ? Math.round(props.value) : Math.round(props.value * 100)
      const c = props.color || (clamped >= 0.8 ? '#22c55e' : clamped >= 0.55 ? '#f59e0b' : '#ef4444')
      const fontSize = props.max === 100 ? (props.size > 70 ? '13px' : '11px') : '11px'
      const dispText = props.max === 100 ? String(dispVal) : `${dispVal}%`
      return h('div', { style: 'display:flex;flex-direction:column;align-items:center;gap:3px;' }, [
        h('svg', { width: props.size, height: props.size, viewBox: '0 0 56 56' }, [
          h('circle', { cx, cy, r, fill: 'none', stroke: '#f1f5f9', 'stroke-width': 5 }),
          h('circle', {
            cx, cy, r, fill: 'none', stroke: c, 'stroke-width': 5,
            'stroke-linecap': 'round',
            'stroke-dasharray': circ,
            'stroke-dashoffset': offset,
            transform: 'rotate(-90 28 28)',
            style: 'transition:stroke-dashoffset .55s ease;',
          }),
          h('text', {
            x: cx, y: cy,
            'text-anchor': 'middle', 'dominant-baseline': 'middle',
            style: `font-size:${fontSize};font-weight:700;fill:${c};`,
          }, dispText),
        ]),
        props.label ? h('div', {
          style: 'font-size:10px;color:#94a3b8;text-align:center;line-height:1.2;max-width:58px;',
        }, props.label) : null,
      ])
    }
  },
})

const configStore = useConfigStore()
const kbList = ref<any[]>([])
const evalMode = ref<'single' | 'compare' | 'variant'>('single')
const compareConfigs = ref<string[]>(['base', 'precision'])
const variants = ref<any[]>([])
const variantDialogOpen = ref(false)
const variantForm = ref({
  config_name: 'base',
  display_name: '',
  top_k_retrieval: 20,
  rerank_top_k: 5,
  enable_multiquery: true,
  enable_query_rewrite: true,
  enable_rerank: true,
  use_jina_reranker: false,
  bm25_weight: 0.3,
})

const form = ref({
  kb_id: '',
  config_name: 'base',
  category_filter: '',
  enable_llm_eval: false,
})

const running = ref(false)
const progress = ref(0)
const progressMsg = ref('')
const progressStatus = ref<'' | 'success' | 'exception'>('')
const singleResult = ref<any>(null)
const compareResults = ref<any[]>([])
const history = ref<any[]>([])
const evalInfo = ref<any>(null)

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

function hasOverrides(name: string): boolean {
  const ov = configStore.getOverrides(name)
  return ov != null && Object.keys(ov).length > 0
}

// ---- 变体管理 ----
function addVariant() {
  const f = variantForm.value
  const parts: string[] = []
  if (!f.enable_multiquery) parts.push('mq=off')
  if (!f.enable_query_rewrite) parts.push('rw=off')
  if (!f.enable_rerank) parts.push('rerank=off')
  if (f.use_jina_reranker) parts.push('jina=on')
  if (f.top_k_retrieval !== 20) parts.push(`topk=${f.top_k_retrieval}`)
  if (f.rerank_top_k !== 5) parts.push(`rk=${f.rerank_top_k}`)
  if (Math.abs(f.bm25_weight - 0.3) > 0.01) parts.push(`bm25=${f.bm25_weight.toFixed(2)}`)
  const autoName = `${f.config_name}:${parts.join(',') || '默认'}`

  variants.value.push({
    config_name: f.config_name,
    display_name: f.display_name || autoName,
    overrides: {
      top_k_retrieval: f.top_k_retrieval,
      rerank_top_k: f.rerank_top_k,
      enable_multiquery: f.enable_multiquery,
      enable_query_rewrite: f.enable_query_rewrite,
      enable_rerank: f.enable_rerank,
      use_jina_reranker: f.use_jina_reranker,
      bm25_weight: f.bm25_weight,
    },
  })
  variantDialogOpen.value = false
}

// ---- 评估运行 ----
async function startEval() {
  running.value = true
  progress.value = 0
  progressMsg.value = '准备中...'
  progressStatus.value = ''
  singleResult.value = null
  compareResults.value = []

  const token = localStorage.getItem('token') ?? ''

  try {
    if (evalMode.value === 'single') {
      const body = {
        config_name: form.value.config_name,
        kb_id: form.value.kb_id || undefined,
        category_filter: form.value.category_filter || undefined,
        enable_llm_eval: form.value.enable_llm_eval,
        overrides: configStore.getOverrides(form.value.config_name),
      }
      const result = await runSingleEval(token, body, (p, msg) => {
        progress.value = p; progressMsg.value = msg
      })
      singleResult.value = result
      progressStatus.value = 'success'
      progressMsg.value = `评估完成，平均延迟 ${result.avg_latency_ms} ms`
    } else if (evalMode.value === 'compare') {
      if (compareConfigs.value.length < 2) {
        progressMsg.value = '请至少选择2个配置'
        progressStatus.value = 'exception'
        return
      }
      const all: any[] = []
      for (const [i, cfg] of compareConfigs.value.entries()) {
        const result = await runSingleEval(token, {
          config_name: cfg,
          kb_id: form.value.kb_id || undefined,
          category_filter: form.value.category_filter || undefined,
          enable_llm_eval: form.value.enable_llm_eval,
          overrides: configStore.getOverrides(cfg),
        }, (p, msg) => {
          const overall = Math.round((i + p / 100) / compareConfigs.value.length * 100)
          progress.value = overall
          progressMsg.value = `[${i+1}/${compareConfigs.value.length}] ${cfg.toUpperCase()}: ${msg}`
        })
        all.push(result)
      }
      compareResults.value = all
      progressStatus.value = 'success'
      progressMsg.value = `对比完成，共 ${all.length} 个配置`
    } else {
      // variant
      if (variants.value.length === 0) {
        progressMsg.value = '请先添加变体'; progressStatus.value = 'exception'; return
      }
      const all: any[] = []
      for (let i = 0; i < variants.value.length; i++) {
        const v = variants.value[i]
        const result = await runSingleEval(token, {
          config_name: v.config_name,
          display_name: v.display_name,
          kb_id: form.value.kb_id || undefined,
          category_filter: form.value.category_filter || undefined,
          enable_llm_eval: form.value.enable_llm_eval,
          overrides: v.overrides,
        }, (p, msg) => {
          const overall = Math.round((i + p / 100) / variants.value.length * 100)
          progress.value = overall
          progressMsg.value = `[${i+1}/${variants.value.length}] ${v.display_name}: ${msg}`
        })
        all.push(result)
      }
      compareResults.value = all
      progressStatus.value = 'success'
      progressMsg.value = `对比完成，共 ${all.length} 个变体`
    }
    await fetchHistory()
  } catch (e: any) {
    progressStatus.value = 'exception'
    progressMsg.value = e.message
  } finally {
    running.value = false
  }
}

async function runSingleEval(
  token: string,
  body: any,
  onProgress: (pct: number, msg: string) => void,
): Promise<any> {
  return new Promise((resolve, reject) => {
    ;(async () => {
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
                onProgress(0, `共 ${evt.total} 题`)
              } else if (evt.stage === 'progress') {
                const pct = Math.round((evt.current / evt.total) * 100)
                onProgress(pct, `[${evt.current}/${evt.total}] ${evt.question}`)
              } else if (evt.stage === 'done') {
                onProgress(100, '完成')
                resolve(evt)
              } else if (evt.stage === 'error') {
                reject(new Error(evt.message))
              }
            } catch { /* ignore parse errors */ }
          }
        }
      } catch (e) { reject(e) }
    })()
  })
}

// ---- 对比表格 ----
const compareMetricKeys = ['hit@1', 'hit@3', 'hit@5', 'recall@5', 'mrr', 'ndcg@5']

const compareTableRows = computed(() =>
  compareResults.value.map(r => ({
    name: (r.config_name ?? r.display_name ?? '').toUpperCase(),
    score: Math.round(r.composite_score ?? 0),
    metrics: r.metrics ?? {},
    latency: r.avg_latency_ms ?? 0,
  }))
)

const bestItems = computed(() => {
  if (!compareResults.value.length) return []
  const items: any[] = []
  for (const key of compareMetricKeys) {
    let best: any = null
    for (const r of compareResults.value) {
      const val = r.metrics?.[key] ?? 0
      if (!best || val > best.val) best = { val, name: (r.config_name ?? '').toUpperCase() }
    }
    if (best && best.val > 0) {
      items.push({ key, label: key.toUpperCase(), winner: best.name, value: fmtPct(best.val) })
    }
  }
  // 最低延迟
  let fastestLatency: any = null
  for (const r of compareResults.value) {
    const lat = r.avg_latency_ms ?? 9999
    if (!fastestLatency || lat < fastestLatency.val) {
      fastestLatency = { val: lat, name: (r.config_name ?? '').toUpperCase() }
    }
  }
  if (fastestLatency) {
    items.push({ key: 'latency', label: '延迟', winner: fastestLatency.name, value: `${Math.round(fastestLatency.val)}ms` })
  }
  return items
})

// ---- 逐题辅助 ----
const singleHitRate = computed(() => {
  if (!singleResult.value?.results) return '-'
  const withHit = singleResult.value.results.filter((r: any) => r.is_hit !== undefined)
  if (!withHit.length) return '-'
  return Math.round(withHit.filter((r: any) => r.is_hit).length / withHit.length * 100)
})

function missedChunks(row: any): string[] {
  if (!row.relevant_chunks?.length) return []
  const retrieved = new Set(row.retrieved_ids ?? [])
  return (row.relevant_chunks as string[]).filter(c => !retrieved.has(c))
}

// ---- 历史趋势摘要 ----
const trendSummary = computed(() => {
  if (history.value.length < 2) return null
  const cur = history.value[0]
  const prev = history.value[1]
  const curScore = Math.round(cur.composite_score ?? 0)
  const prevScore = Math.round(prev.composite_score ?? 0)
  const diff = curScore - prevScore
  return {
    cur_config: (cur.config_name ?? '').toUpperCase(),
    prev_config: (prev.config_name ?? '').toUpperCase(),
    cur_score: curScore,
    prev_score: prevScore,
    diff,
    arrow: diff > 0 ? '📈' : diff < 0 ? '📉' : '➡️',
  }
})

// ---- 指标元数据 ----
const METRIC_INFO: Record<string, { help: string; thresholds: [number, number]; low_reasons: string[]; optimize: string[] }> = {
  'recall@1': {
    help: 'Top-1 结果命中数占预期总数的比例',
    thresholds: [0.4, 0.2],
    low_reasons: ['预期 chunk 数多时，Recall@1 天然低', '未启用 Rerank，正确 chunk 排不进第一位', 'chunk 切分过细，答案被拆到多个 chunk'],
    optimize: ['启用 Rerank 精排（enable_rerank）', '增大 top_k_retrieval 扩大候选池', '关注 Hit@1 更直观'],
  },
  'hit@1': {
    help: 'Top-1 结果是否命中至少一个预期 chunk。最直观的检索质量指标',
    thresholds: [0.8, 0.6],
    low_reasons: ['未启用 Rerank，正确 chunk 在候选集但排不进第一位', '正确 chunk 未被检索到（Embedding/BM25 匹配差）'],
    optimize: ['启用 Rerank 精排 — 最有效', '增大 top_k_retrieval 扩大候选池'],
  },
  'hit@3': {
    help: 'Top-3 结果中是否至少命中一个预期 chunk',
    thresholds: [0.85, 0.7],
    low_reasons: ['正确 chunk 被噪音结果挤出 Top-3', '召回面不够广，正确 chunk 未进入候选集'],
    optimize: ['启用 Rerank 精排', '启用 MultiQuery 扩展', '增大 top_k_retrieval（如 20→30）'],
  },
  'hit@5': {
    help: 'Top-5 结果中是否至少命中一个预期 chunk。核心检索质量指标',
    thresholds: [0.9, 0.75],
    low_reasons: ['正确 chunk 未进入候选集（top_k 太小或语义匹配差）', 'Embedding 模型对中文语义理解不足', 'PDF 解析丢失关键信息'],
    optimize: ['启用 MultiQuery 扩展', '增大 top_k_retrieval（如 20→50）', '检查 Embedding 模型是否与文档语言匹配'],
  },
  'recall@3': {
    help: 'Top-3 结果命中数占预期总数的比例',
    thresholds: [0.5, 0.3],
    low_reasons: ['未启用 Rerank，正确 chunk 被噪音结果挤出 Top-3', '召回面不够广'],
    optimize: ['启用 Rerank 精排', '启用 MultiQuery 扩展', '增大 top_k_retrieval'],
  },
  'recall@5': {
    help: 'Top-5 检索结果中包含正确答案的比例',
    thresholds: [0.8, 0.6],
    low_reasons: ['正确 chunk 未进入候选集（top_k 太小或语义匹配差）', 'MultiQuery 未启用或扩展质量差', 'Embedding 模型对中文语义理解不足'],
    optimize: ['启用 MultiQuery 扩展', '增大 top_k_retrieval（如 20→50）', '启用 Rerank 精排', '检查 Embedding 模型'],
  },
  'mrr': {
    help: '平均倒排名。第一个正确结果排在第几位的倒数均值',
    thresholds: [0.8, 0.6],
    low_reasons: ['未启用 Rerank，正确结果被噪音结果挤到后面', '存在大量语义相似但不相关的噪音结果'],
    optimize: ['启用 Rerank 精排', '调整 BM25 权重加强关键词精确匹配', '优化 chunk 切分策略'],
  },
  'ndcg@5': {
    help: '归一化折损累计增益。综合考虑相关性和排序位置',
    thresholds: [0.75, 0.55],
    low_reasons: ['相关结果排序靠后，被噪音结果挤出前列', 'Top-5 中有大量不相关结果'],
    optimize: ['启用 Rerank 精排', '启用 MultiQuery 扩展', '优化 chunk 质量'],
  },
}

function metricInfo(key: string) {
  return METRIC_INFO[key] ?? { help: '', thresholds: [0.8, 0.6] as [number, number], low_reasons: [], optimize: [] }
}

function metricHelp(key: string): string { return metricInfo(key).help }

function metricThresholds(key: string): [number, number] {
  return metricInfo(key).thresholds
}

function metricColor(val: number, key: string): string {
  const [good, ok] = metricThresholds(key)
  if (val >= good) return '#67c23a'
  if (val >= ok) return '#e6a23c'
  return '#f56c6c'
}

function metricEmoji(val: number, key: string): string {
  const [good, ok] = metricThresholds(key)
  if (val >= good) return '🟢 优秀'
  if (val >= ok) return '🟡 良好'
  return '🔴 需优化'
}

function metricNeedsAnalysis(val: number, key: string): boolean {
  const [good] = metricThresholds(key)
  return val < good && val > 0  // 不展示未计算（=0）的指标
}

function metricLevelType(val: number, key: string): '' | 'success' | 'warning' | 'danger' {
  const [good, ok] = metricThresholds(key)
  if (val >= good) return 'success'
  if (val >= ok) return 'warning'
  return 'danger'
}

function mainMetricCards(metrics: Record<string, number> | undefined) {
  if (!metrics) return []
  return [
    { key: 'hit@1', label: 'Hit@1', val: metrics['hit@1'] ?? 0 },
    { key: 'hit@3', label: 'Hit@3', val: metrics['hit@3'] ?? 0 },
    { key: 'hit@5', label: 'Hit@5', val: metrics['hit@5'] ?? 0 },
    { key: 'recall@5', label: 'Recall@5', val: metrics['recall@5'] ?? 0 },
    { key: 'mrr', label: 'MRR', val: metrics['mrr'] ?? 0 },
    { key: 'ndcg@5', label: 'NDCG@5', val: metrics['ndcg@5'] ?? 0 },
    { key: 'faithfulness', label: 'Faithfulness', val: metrics['faithfulness'] ?? 0 },
  ]
}

function fmtPct(v: number): string {
  if (v === undefined || v === null) return '-'
  return (v * 100).toFixed(1) + '%'
}
function fmtHistPct(v: number | undefined): string {
  if (v === undefined || v === null) return '-'
  return (v * 100).toFixed(1) + '%'
}

function scoreColor(s: number): string {
  if (s >= 75) return '#67c23a'
  if (s >= 55) return '#e6a23c'
  return '#f56c6c'
}
function scoreLevel(s: number): string {
  if (s >= 75) return '优秀'
  if (s >= 55) return '良好'
  return '需优化'
}
function scoreLevelType(s: number): '' | 'success' | 'warning' | 'danger' {
  if (s >= 75) return 'success'
  if (s >= 55) return 'warning'
  return 'danger'
}
function latencyColor(ms: number): string {
  if (ms < 500) return '#67c23a'
  if (ms < 1500) return '#e6a23c'
  return '#f56c6c'
}
function latencyEmoji(ms: number): string {
  if (ms < 500) return '🟢 优秀'
  if (ms < 1500) return '🟡 良好'
  return '🔴 偏慢'
}
</script>

<style scoped>
.page-container {
  padding: 24px 28px; height: 100%; overflow-y: auto;
  box-sizing: border-box; background: #f8fafc;
}
.page-header { display: flex; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; font-weight: 700; color: #0f172a; letter-spacing: -.3px; }

/* Score card */
.score-card {
  background: linear-gradient(135deg, rgba(59,130,246,.05), rgba(34,197,94,.05)) !important;
  border: 1px solid #e8edf3 !important;
}
.score-layout { display: flex; align-items: center; gap: 28px; }
.score-left { display: flex; flex-direction: column; align-items: center; gap: 4px; flex-shrink: 0; }
.score-subtitle { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.score-divider {
  width: 1px; height: 80px; background: #e8edf3; flex-shrink: 0;
}
.score-metrics {
  flex: 1; display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start;
}

/* Metric cell */
.metric-cell { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.metric-label { font-size: 10px; color: #94a3b8; text-align: center; }
.metric-level { font-size: 10px; text-align: center; }

/* Latency cell */
.latency-cell { justify-content: center; min-width: 54px; }
.latency-val { font-size: 20px; font-weight: 700; line-height: 1; }

.trend-summary {
  padding: 10px 14px; background: #f8fafc; border-radius: 8px;
  font-size: 13px; color: #475569; margin-bottom: 12px;
  border: 1px solid #e8edf3;
}
</style>
