<template>
  <div class="page-container" v-loading="pageLoading">
    <div class="page-header">
      <div style="display:flex; align-items:center; gap:12px;">
        <el-button :icon="ArrowLeft" circle @click="router.back()" />
        <div>
          <h2 style="margin:0;">{{ kb?.name }}</h2>
          <span style="color:#909399; font-size:13px;">{{ kb?.description }}</span>
        </div>
      </div>
      <el-tag :type="statusType" size="large">{{ statusLabel }}</el-tag>
    </div>

    <el-tabs v-model="activeTab">
      <!-- Tab 1: 文件管理 -->
      <el-tab-pane label="📁 文件管理" name="files">
        <div style="display:flex; gap:12px; margin-bottom:16px; align-items:center; flex-wrap:wrap;">
          <el-upload
            :show-file-list="false"
            :before-upload="beforeUpload"
            :http-request="doUpload"
            multiple
            accept=".pdf,.json"
          >
            <el-button type="primary" :icon="Upload">上传文件</el-button>
          </el-upload>
          <el-button type="success" :loading="jobLoading" @click="startProcess" :icon="VideoPlay">
            一键处理（解析+索引）
          </el-button>
          <el-button @click="startParse" :loading="jobLoading">仅解析</el-button>
          <el-button @click="startIndex" :loading="jobLoading">仅构建索引</el-button>
        </div>

        <el-table :data="docs" v-loading="docsLoading" style="width:100%;">
          <el-table-column label="文件名" prop="filename" min-width="200" />
          <el-table-column label="类型" prop="file_type" width="70" />
          <el-table-column label="大小" width="90">
            <template #default="{ row }">{{ (row.file_size / 1024).toFixed(1) }} KB</template>
          </el-table-column>
          <el-table-column label="解析状态" width="110">
            <template #default="{ row }">
              <el-tag :type="parseTagType(row.parse_status)" size="small">
                {{ parseLabel(row.parse_status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Chunks" prop="chunk_count" width="80" />
          <el-table-column label="上传时间" min-width="160">
            <template #default="{ row }">{{ row.upload_time.slice(0, 16).replace('T', ' ') }}</template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="downloadFile(row)">下载</el-button>
              <el-button text type="success" size="small" @click="viewParsed(row)"
                :disabled="row.parse_status !== 'done'">查看解析</el-button>
              <el-button text type="danger" size="small" @click="deleteFile(row.doc_id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 2: 任务状态 -->
      <el-tab-pane label="⚙️ 处理状态" name="jobs">
        <el-button :icon="Refresh" circle @click="fetchJobs" style="margin-bottom:12px;" />
        <el-timeline>
          <el-timeline-item
            v-for="job in jobs" :key="job.job_id"
            :type="jobTimelineType(job.status)"
            :timestamp="(job.started_at ?? '').slice(0, 16).replace('T', ' ')"
          >
            <el-card shadow="never" style="padding:10px 16px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:600;">{{ job.job_type.toUpperCase() }}</span>
                <el-tag :type="jobTagType(job.status)" size="small">{{ job.status }}</el-tag>
              </div>
              <el-progress v-if="job.status === 'running'" :percentage="Math.round(job.progress * 100)"
                style="margin-top:8px;" />
              <div style="color:#909399; font-size:13px; margin-top:4px;">
                {{ job.stage_msg || job.error_msg || '' }}
              </div>
            </el-card>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-if="jobs.length === 0" description="暂无任务" />
      </el-tab-pane>

      <!-- 解析结果弹窗 -->
    <el-dialog v-model="parsedVisible" :title="`解析结果 — ${parsedData?.filename ?? ''}`" width="80%" top="5vh"
      destroy-on-close>
      <div v-if="parsedLoading" v-loading="true" style="height:200px;"></div>
      <div v-else-if="parsedData">
        <div style="margin-bottom:12px; color:#909399; font-size:13px;">
          共 {{ parsedData.total_pages }} 页，{{ parsedData.pages.length }} 个文本块
        </div>
        <el-tabs v-model="parsedTab" type="card">
          <el-tab-pane label="按页查看" name="pages">
            <div v-for="p in parsedData.pages" :key="p.page"
              style="margin-bottom:16px; border:1px solid #ebeef5; border-radius:8px; padding:12px;">
              <div style="font-weight:600; color:#409eff; margin-bottom:8px;">第 {{ p.page }} 页</div>
              <pre style="white-space:pre-wrap; word-break:break-all; font-size:13px; color:#303133; margin:0; max-height:400px; overflow-y:auto;">{{ p.text }}</pre>
            </div>
          </el-tab-pane>
          <el-tab-pane label="完整 Markdown" name="markdown">
            <pre style="white-space:pre-wrap; word-break:break-all; font-size:13px; color:#303133; max-height:70vh; overflow-y:auto;">{{ parsedData.markdown }}</pre>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>

      <!-- Tab 3: 配置 -->
      <el-tab-pane label="🔧 配置" name="config">
        <el-descriptions :column="2" border style="margin-bottom:20px;">
          <el-descriptions-item label="知识库 ID">{{ kb?.kb_id }}</el-descriptions-item>
          <el-descriptions-item label="配置预设">{{ kb?.config_name }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ kb?.status }}</el-descriptions-item>
          <el-descriptions-item label="文件数">{{ kb?.doc_count }}</el-descriptions-item>
          <el-descriptions-item label="Chunk 数">{{ kb?.chunk_count }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ kb?.created_at.slice(0, 16).replace('T', ' ') }}
          </el-descriptions-item>
        </el-descriptions>

        <h3 style="margin:16px 0 12px;">分片配置</h3>
        <el-alert type="info" :closable="false" style="margin-bottom:16px;">
          修改分片参数后需点击「保存」并重新处理知识库才能生效。
        </el-alert>
        <el-form label-width="140px" style="max-width:500px;">
          <el-form-item label="分片策略">
            <el-select v-model="splitForm.split_method" style="width:100%;">
              <el-option label="固定大小 + 边界检测" value="fixed" />
              <el-option label="递归分割（段落→句子→字符）" value="recursive" />
              <el-option label="句子边界" value="sentence" />
              <el-option label="滑动窗口" value="sliding" />
            </el-select>
          </el-form-item>
          <el-form-item label="Chunk 大小">
            <el-input-number v-model="splitForm.chunk_size" :min="100" :max="2000" :step="50" />
            <span style="color:#909399; margin-left:8px;">字符</span>
          </el-form-item>
          <el-form-item label="Chunk 重叠">
            <el-input-number v-model="splitForm.chunk_overlap" :min="0" :max="500" :step="10" />
            <span style="color:#909399; margin-left:8px;">字符</span>
          </el-form-item>
          <el-form-item label="父 Chunk 大小">
            <el-input-number v-model="splitForm.parent_chunk_size" :min="500" :max="5000" :step="100" />
            <span style="color:#909399; margin-left:8px;">字符</span>
          </el-form-item>
          <el-form-item label="父子检索">
            <el-switch v-model="splitForm.enable_parent_retrieval" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="savingConfig" @click="saveSplitConfig">保存</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Upload, VideoPlay, Refresh } from '@element-plus/icons-vue'
import { kbApi, type KB, type Doc, type Job } from '@/api/kb'

const route = useRoute()
const router = useRouter()
const kbId = route.params.id as string

const pageLoading = ref(true)
const docsLoading = ref(false)
const jobLoading = ref(false)
const activeTab = ref('files')
const kb = ref<KB | null>(null)
const docs = ref<Doc[]>([])
const jobs = ref<Job[]>([])
let pollTimer: ReturnType<typeof setInterval> | null = null

const parsedVisible = ref(false)
const parsedLoading = ref(false)
const parsedData = ref<{ filename: string; total_pages: number; pages: any[]; markdown: string } | null>(null)
const parsedTab = ref('pages')

const savingConfig = ref(false)
const splitForm = ref({
  chunk_size: 500,
  chunk_overlap: 150,
  parent_chunk_size: 800,
  split_method: 'fixed',
  enable_parent_retrieval: true,
})

onMounted(async () => {
  await Promise.all([fetchKB(), fetchDocs(), fetchJobs()])
  pageLoading.value = false
  startPoll()
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

async function fetchKB() {
  const res = await kbApi.get(kbId)
  kb.value = res.data
  // 同步分片配置到表单
  splitForm.value = {
    chunk_size: res.data.chunk_size ?? 500,
    chunk_overlap: res.data.chunk_overlap ?? 150,
    parent_chunk_size: res.data.parent_chunk_size ?? 800,
    split_method: res.data.split_method || 'fixed',
    enable_parent_retrieval: res.data.enable_parent_retrieval ?? true,
  }
}
async function fetchDocs() {
  docsLoading.value = true
  try { const res = await kbApi.listFiles(kbId); docs.value = res.data }
  finally { docsLoading.value = false }
}
async function fetchJobs() {
  const res = await kbApi.listJobs(kbId)
  jobs.value = res.data
}

function startPoll() {
  // 每 3s 刷新一次任务状态，有 running 任务时才持续
  pollTimer = setInterval(async () => {
    const hasRunning = jobs.value.some(j => j.status === 'running' || j.status === 'pending')
    if (hasRunning) { await fetchJobs(); await fetchKB() }
  }, 3000)
}

function beforeUpload() { return true }
async function doUpload({ file }: { file: File }) {
  try {
    await kbApi.uploadFile(kbId, file)
    ElMessage.success(`${file.name} 上传成功`)
    await fetchDocs(); await fetchKB()
  } catch { /* 已统一提示 */ }
}

async function startProcess() {
  jobLoading.value = true
  try { await kbApi.process(kbId); ElMessage.success('处理任务已启动'); await fetchJobs() }
  finally { jobLoading.value = false }
}
async function startParse() {
  jobLoading.value = true
  try { await kbApi.parse(kbId); ElMessage.success('解析任务已启动'); await fetchJobs() }
  finally { jobLoading.value = false }
}
async function startIndex() {
  jobLoading.value = true
  try { await kbApi.index(kbId); ElMessage.success('索引任务已启动'); await fetchJobs() }
  finally { jobLoading.value = false }
}

async function deleteFile(docId: string) {
  await kbApi.deleteFile(kbId, docId)
  ElMessage.success('已删除')
  await fetchDocs(); await fetchKB()
}

function downloadFile(doc: Doc) {
  const url = kbApi.downloadFile(kbId, doc.doc_id)
  const a = document.createElement('a')
  a.href = url
  a.download = doc.filename
  a.click()
}

async function viewParsed(doc: Doc) {
  parsedVisible.value = true
  parsedLoading.value = true
  parsedData.value = null
  parsedTab.value = 'pages'
  try {
    const res = await kbApi.getParsedContent(kbId, doc.doc_id)
    parsedData.value = res.data
  } catch {
    ElMessage.error('获取解析结果失败')
    parsedVisible.value = false
  } finally {
    parsedLoading.value = false
  }
}

async function saveSplitConfig() {
  savingConfig.value = true
  try {
    await kbApi.update(kbId, { ...splitForm.value })
    ElMessage.success('分片配置已保存，重新处理知识库后生效')
    await fetchKB()
  } catch { /* 已统一提示 */ }
  finally { savingConfig.value = false }
}

const statusType = computed(() =>
  ({ ready: 'success', processing: 'warning', error: 'danger', empty: 'info' }[kb.value?.status ?? ''] ?? 'info'))
const statusLabel = computed(() =>
  ({ ready: '就绪', processing: '处理中', error: '出错', empty: '空' }[kb.value?.status ?? ''] ?? ''))

function parseTagType(s: string) {
  return { done: 'success', processing: 'warning', failed: 'danger', pending: 'info' }[s] ?? 'info'
}
function parseLabel(s: string) {
  return { done: '完成', processing: '处理中', failed: '失败', pending: '待处理' }[s] ?? s
}
function jobTagType(s: string) {
  return { done: 'success', running: 'warning', failed: 'danger', pending: 'info' }[s] ?? 'info'
}
function jobTimelineType(s: string): 'success' | 'warning' | 'danger' | 'info' {
  return ({ done: 'success', running: 'warning', failed: 'danger', pending: 'info' }[s] ?? 'info') as any
}
</script>

<style scoped>
.page-container { padding: 24px; height: 100%; overflow-y: auto; box-sizing: border-box; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
</style>
