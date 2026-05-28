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

    <!-- Bad Case 列表 -->
    <el-card>
      <template #header>
        <div style="display:flex; align-items:center; gap:12px;">
          <span>Bad Case 列表</span>
          <el-input
            v-model="keyword"
            placeholder="关键词筛选"
            clearable
            style="width:200px;"
            @change="fetchBadCases"
          />
          <el-button :icon="Download" @click="exportBadCases" style="margin-left:auto;">
            导出
          </el-button>
        </div>
      </template>

      <el-empty v-if="badCases.length === 0" description="暂无 Bad Case" />
      <el-table v-else :data="badCases" stripe style="width:100%;">
        <el-table-column type="index" width="50" />
        <el-table-column label="问题" prop="query" min-width="200" />
        <el-table-column label="答案" prop="answer" min-width="280" show-overflow-tooltip />
        <el-table-column label="备注" prop="comment" width="160" show-overflow-tooltip />
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
        layout="prev,pager,next"
        style="margin-top:12px; justify-content:flex-end; display:flex;"
        @current-change="(p: number) => { page = p; fetchBadCases() }"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Refresh, Download } from '@element-plus/icons-vue'
import http from '@/api/http'

const stats = ref({ total: 0, good: 0, bad: 0, good_rate: 0 })
const badCases = ref<any[]>([])
const badTotal = ref(0)
const keyword = ref('')
const page = ref(1)
const pageSize = 20

onMounted(fetchAll)

async function fetchAll() {
  await Promise.all([fetchStats(), fetchBadCases()])
}

async function fetchStats() {
  try {
    const res = await http.get('/monitor/stats')
    stats.value = res.data
  } catch { /* ignore */ }
}

async function fetchBadCases() {
  try {
    const offset = (page.value - 1) * pageSize
    const res = await http.get('/monitor/bad-cases', {
      params: { limit: pageSize, offset, keyword: keyword.value || undefined },
    })
    badCases.value = res.data.items
    badTotal.value = res.data.total
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
</script>

<style scoped>
.page-container { padding: 24px; height: 100%; overflow-y: auto; box-sizing: border-box; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-header h2 { margin: 0; }
</style>
