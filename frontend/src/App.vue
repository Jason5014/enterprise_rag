<template>
  <router-view v-if="route.meta.public" />
  <div v-else class="app-shell">

    <!-- ───────── 侧边栏 ───────── -->
    <aside class="sidebar">
      <!-- 品牌 -->
      <div class="brand">
        <div class="brand-icon">🧠</div>
        <div class="brand-text">
          <div class="brand-name">企业知识库</div>
          <div class="brand-sub">RAG · Powered by AI</div>
        </div>
      </div>

      <!-- 导航 -->
      <nav class="nav">
        <router-link v-for="item in navItems" :key="item.path"
          :to="item.path" class="nav-item" :class="{ active: route.path === item.path }">
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="route.path === item.path" class="nav-pip" />
        </router-link>
      </nav>

      <div class="sidebar-divider" />

      <!-- 系统状态 -->
      <div class="section" v-if="systemStatus">
        <div class="section-title">系统状态</div>
        <div class="status-grid">
          <div class="status-item">
            <span class="status-dot" :class="systemStatus.vector_ready ? 'ok' : 'warn'" />
            <span class="status-key">向量库</span>
            <span class="status-val">{{ systemStatus.vector_ready ? '就绪' : '未就绪' }}</span>
          </div>
          <div class="status-item">
            <span class="status-dot ok" />
            <span class="status-key">文档</span>
            <span class="status-val">{{ systemStatus.pdf_count }} 份</span>
          </div>
          <div class="status-item">
            <span class="status-dot ok" />
            <span class="status-key">分块</span>
            <span class="status-val">{{ systemStatus.chunk_count }}</span>
          </div>
          <div class="status-item">
            <span class="status-dot ok" />
            <span class="status-key">知识库</span>
            <span class="status-val">{{ systemStatus.kb_count }} 个</span>
          </div>
        </div>
      </div>

      <div class="sidebar-divider" />

      <!-- 检索配置 -->
      <div class="section">
        <div class="section-title">检索配置</div>
        <el-select v-model="configStore.activeConfigName" size="small"
          class="config-select" @change="onConfigChange">
          <el-option v-for="(label, key) in CONFIG_LABELS" :key="key" :label="label" :value="key" />
        </el-select>

        <!-- 功能徽章 -->
        <div v-if="configStore.defaultsLoaded" class="badge-row">
          <el-tooltip v-for="item in configBadges" :key="item.key" :content="item.label" placement="right">
            <span class="mini-badge" :class="item.on ? 'on' : 'off'">{{ item.icon }}</span>
          </el-tooltip>
        </div>

        <div class="config-actions">
          <button class="action-btn primary" @click="drawerOpen = true">✏️ 编辑配置</button>
          <button class="action-btn" @click="resetConfig" :disabled="!configStore.hasOverrides"
            :title="configStore.hasOverrides ? '恢复预设默认值' : ''">↺</button>
        </div>
        <div v-if="configStore.hasOverrides" class="override-hint">⚡ 含自定义参数</div>
      </div>

      <!-- 弹性占位 -->
      <div style="flex:1;" />

      <!-- 用户 -->
      <div class="user-bar">
        <div class="user-avatar">{{ userInitial }}</div>
        <span class="user-name">{{ authStore.user?.username ?? '...' }}</span>
        <button class="logout-btn" @click="handleLogout" title="退出登录">⏏</button>
      </div>
    </aside>

    <!-- 主内容 -->
    <main class="main-content">
      <router-view />
    </main>

    <!-- 配置 Drawer -->
    <ConfigDrawer v-model="drawerOpen" :config-name="configStore.activeConfigName" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useConfigStore, CONFIG_LABELS } from '@/stores/config'
import ConfigDrawer from '@/components/ConfigDrawer.vue'
import http from '@/api/http'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const configStore = useConfigStore()
const drawerOpen = ref(false)
const systemStatus = ref<any>(null)

const navItems = [
  { path: '/qa',      icon: '💬', label: '问答助手' },
  { path: '/kb',      icon: '📚', label: '知识库管理' },
  { path: '/eval',    icon: '📊', label: '评估测试' },
  { path: '/monitor', icon: '📡', label: '质量监控' },
]

onMounted(async () => {
  if (authStore.isLoggedIn() && !authStore.user) await authStore.fetchMe()
  await Promise.all([configStore.fetchPresetDefaults(), fetchSystemStatus()])
})

async function fetchSystemStatus() {
  try { const r = await http.get('/system/status'); systemStatus.value = r.data } catch { /* ignore */ }
}

function onConfigChange() { configStore.resetOverrides(configStore.activeConfigName) }
function resetConfig() { configStore.resetOverrides(configStore.activeConfigName) }
function handleLogout() { authStore.logout(); router.push('/login') }

const userInitial = computed(() => ((authStore.user?.username ?? 'U')[0] ?? 'U').toUpperCase())

const configBadges = computed(() => {
  const eff = configStore.activeEffective
  return [
    { key: 'parent', icon: '📎', label: '父子块检索', on: eff.enable_parent_retrieval ?? true },
    { key: 'history', icon: '💬', label: '对话历史', on: eff.enable_history ?? true },
    { key: 'mq', icon: '🔄', label: 'MultiQuery 扩展', on: eff.enable_multiquery ?? true },
    { key: 'rw', icon: '✏️', label: 'Query 改写', on: eff.enable_query_rewrite ?? true },
    { key: 'rerank', icon: '🗳️', label: 'Rerank 精排', on: eff.enable_rerank ?? true },
  ]
})
</script>

<style scoped>
.app-shell { display: flex; height: 100vh; overflow: hidden; }

/* ── Sidebar ── */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid var(--sidebar-border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 12px;
  flex-shrink: 0;
}
.brand-icon {
  width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
}
.brand-name { font-size: 14px; font-weight: 700; color: var(--sidebar-text-bright); letter-spacing: -.2px; }
.brand-sub { font-size: 10px; color: var(--sidebar-text); margin-top: 1px; letter-spacing: .5px; }

.nav { display: flex; flex-direction: column; gap: 2px; padding: 4px 10px; flex-shrink: 0; }
.nav-item {
  display: flex; align-items: center; gap: 9px; padding: 8px 10px;
  border-radius: 8px; color: var(--sidebar-text); text-decoration: none;
  font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all .16s ease; position: relative;
}
.nav-item:hover { background: rgba(51,65,85,.35); color: var(--sidebar-text-bright); }
.nav-item.active { background: var(--sidebar-active-bg); color: #93c5fd; }
.nav-icon { font-size: 14px; width: 18px; text-align: center; flex-shrink: 0; }
.nav-label { flex: 1; }
.nav-pip {
  position: absolute; right: 0; top: 50%; transform: translateY(-50%);
  width: 3px; height: 20px; background: #3b82f6; border-radius: 3px 0 0 3px;
}

.sidebar-divider { border-top: 1px solid var(--sidebar-border); margin: 6px 0; flex-shrink: 0; }

.section { padding: 4px 14px 8px; flex-shrink: 0; }
.section-title {
  font-size: 10px; font-weight: 600; color: var(--sidebar-text);
  letter-spacing: .8px; text-transform: uppercase; margin-bottom: 8px;
}

.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 6px; }
.status-item { display: flex; align-items: center; gap: 4px; font-size: 11px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.status-dot.ok { background: #22c55e; box-shadow: 0 0 5px rgba(34,197,94,.5); }
.status-dot.warn { background: #f59e0b; box-shadow: 0 0 5px rgba(245,158,11,.5); }
.status-key { color: var(--sidebar-text); }
.status-val { color: var(--sidebar-text-bright); font-weight: 500; margin-left: auto; }

.config-select { width: 100%; }
:deep(.config-select .el-input__wrapper) {
  background: rgba(30,41,59,.6) !important;
  border: 1px solid rgba(51,65,85,.6) !important;
  box-shadow: none !important;
}
:deep(.config-select .el-input__inner) { color: var(--sidebar-text-bright) !important; font-size: 12px !important; }
:deep(.config-select .el-select__caret) { color: var(--sidebar-text) !important; }

.badge-row { display: flex; gap: 4px; flex-wrap: wrap; margin: 8px 0 6px; }
.mini-badge {
  width: 26px; height: 26px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; cursor: default; transition: opacity .16s;
}
.mini-badge.on { background: rgba(34,197,94,.12); opacity: 1; }
.mini-badge.off { background: rgba(51,65,85,.25); opacity: .4; filter: grayscale(1); }

.config-actions { display: flex; gap: 5px; }
.action-btn {
  flex: 1; padding: 5px 6px; border-radius: 6px;
  border: 1px solid rgba(51,65,85,.5);
  background: rgba(30,41,59,.4); color: var(--sidebar-text);
  font-size: 11px; font-weight: 500; cursor: pointer;
  transition: all .16s; white-space: nowrap; text-align: center;
}
.action-btn:hover { background: rgba(59,130,246,.15); color: #93c5fd; border-color: rgba(59,130,246,.4); }
.action-btn.primary { color: #93c5fd; }
.action-btn:disabled { opacity: .3; cursor: not-allowed; }
.override-hint { font-size: 10px; color: #fbbf24; margin-top: 4px; }

.user-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 14px; border-top: 1px solid var(--sidebar-border); flex-shrink: 0;
}
.user-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: #fff; flex-shrink: 0;
}
.user-name {
  flex: 1; font-size: 12px; color: var(--sidebar-text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.logout-btn {
  background: none; border: none; color: var(--sidebar-text);
  cursor: pointer; font-size: 14px; padding: 3px 4px;
  border-radius: 4px; transition: color .16s; flex-shrink: 0;
}
.logout-btn:hover { color: #f87171; }

.main-content { flex: 1; overflow: hidden; background: #f8fafc; }
</style>
