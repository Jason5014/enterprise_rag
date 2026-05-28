<template>
  <div class="page-container">
    <div class="page-header">
      <h2>知识库管理</h2>
      <el-button type="primary" :icon="Plus" @click="showCreate = true">新建知识库</el-button>
    </div>

    <el-row :gutter="16" v-loading="loading">
      <!-- 空状态 -->
      <el-col :span="24" v-if="!loading && kbs.length === 0">
        <el-empty description="暂无知识库，点击右上角新建" />
      </el-col>

      <el-col :xs="24" :sm="12" :lg="8" v-for="kb in kbs" :key="kb.kb_id" style="margin-bottom:16px;">
        <el-card class="kb-card" shadow="hover" @click="router.push(`/kb/${kb.kb_id}`)">
          <div class="kb-card-header">
            <span class="kb-name">{{ kb.name }}</span>
            <el-tag :type="statusTagType(kb.status)" size="small">{{ statusLabel(kb.status) }}</el-tag>
          </div>
          <div class="kb-desc">{{ kb.description || '暂无描述' }}</div>
          <div class="kb-meta">
            <span><el-icon><Document /></el-icon> {{ kb.doc_count }} 文件</span>
            <span><el-icon><Coin /></el-icon> {{ kb.chunk_count }} 块</span>
            <span style="margin-left:auto; color:#c0c4cc;">{{ kb.config_name }}</span>
          </div>
          <div class="kb-actions" @click.stop>
            <el-button text type="danger" size="small" @click="handleDelete(kb)">删除</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 新建对话框 -->
    <el-dialog v-model="showCreate" title="新建知识库" width="480px">
      <el-form :model="createForm" label-position="top">
        <el-form-item label="知识库名称" required>
          <el-input v-model="createForm.name" placeholder="例：2024年报知识库" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
        <el-form-item label="配置预设">
          <el-select v-model="createForm.config_name" style="width:100%;">
            <el-option label="基础 (base)" value="base" />
            <el-option label="快速 (fast)" value="fast" />
            <el-option label="精准 (precision)" value="precision" />
            <el-option label="完整 (full)" value="full" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { kbApi, type KB } from '@/api/kb'

const router = useRouter()
const loading = ref(false)
const creating = ref(false)
const showCreate = ref(false)
const kbs = ref<KB[]>([])

const createForm = reactive({ name: '', description: '', config_name: 'base' })

onMounted(fetchList)

async function fetchList() {
  loading.value = true
  try {
    const res = await kbApi.list()
    kbs.value = res.data
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  if (!createForm.name.trim()) { ElMessage.warning('请输入知识库名称'); return }
  creating.value = true
  try {
    await kbApi.create(createForm)
    ElMessage.success('创建成功')
    showCreate.value = false
    createForm.name = ''; createForm.description = ''
    await fetchList()
  } finally {
    creating.value = false
  }
}

async function handleDelete(kb: KB) {
  await ElMessageBox.confirm(`确认删除知识库"${kb.name}"？此操作不可撤销。`, '删除确认',
    { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' })
  await kbApi.delete(kb.kb_id)
  ElMessage.success('已删除')
  await fetchList()
}

function statusTagType(s: string) {
  return { ready: 'success', processing: 'warning', error: 'danger', empty: 'info' }[s] ?? 'info'
}
function statusLabel(s: string) {
  return { ready: '就绪', processing: '处理中', error: '出错', empty: '空' }[s] ?? s
}
</script>

<style scoped>
.page-container { padding: 24px; height: 100%; overflow-y: auto; box-sizing: border-box; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-header h2 { margin: 0; }
.kb-card { cursor: pointer; transition: transform .15s; }
.kb-card:hover { transform: translateY(-2px); }
.kb-card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.kb-name { font-size: 15px; font-weight: 600; }
.kb-desc { color: #909399; font-size: 13px; margin-bottom: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kb-meta { display: flex; gap: 12px; font-size: 13px; color: #606266; align-items: center; }
.kb-meta span { display: flex; align-items: center; gap: 4px; }
.kb-actions { margin-top: 10px; text-align: right; }
</style>
