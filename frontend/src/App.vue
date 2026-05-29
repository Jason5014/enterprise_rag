<template>
  <router-view v-if="route.meta.public" />
  <el-container v-else style="height: 100vh;">

    <!-- 左侧导航 -->
    <el-aside width="220px" style="background:#1a2332; display:flex; flex-direction:column; overflow:hidden;">
      <!-- Logo -->
      <div style="padding:18px 16px 10px; color:#fff; font-size:15px; font-weight:700; letter-spacing:0.5px; flex-shrink:0;">
        🧠 企业知识库
      </div>

      <!-- 导航菜单 -->
      <el-menu
        :default-active="route.path"
        router
        background-color="#1a2332"
        text-color="#b0bec5"
        active-text-color="#64b5f6"
        style="border:none; flex-shrink:0;"
      >
        <el-menu-item index="/qa">
          <el-icon><ChatDotRound /></el-icon>
          <span>问答助手</span>
        </el-menu-item>
        <el-menu-item index="/kb">
          <el-icon><Files /></el-icon>
          <span>知识库管理</span>
        </el-menu-item>
        <el-menu-item index="/eval">
          <el-icon><DataAnalysis /></el-icon>
          <span>评估测试</span>
        </el-menu-item>
        <el-menu-item index="/monitor">
          <el-icon><Monitor /></el-icon>
          <span>质量监控</span>
        </el-menu-item>
      </el-menu>

      <!-- 分隔线 -->
      <div style="border-top:1px solid #2d3e50; margin:8px 0; flex-shrink:0;" />

      <!-- 系统状态 -->
      <div style="padding:8px 14px; flex-shrink:0;">
        <div style="font-size:11px; color:#546e7a; font-weight:600; margin-bottom:6px; text-transform:uppercase; letter-spacing:0.5px;">
          系统状态
        </div>
        <div v-if="systemStatus" style="display:flex; flex-direction:column; gap:4px;">
          <div class="status-row">
            <span class="status-label">📄 文档</span>
            <span class="status-val">{{ systemStatus.pdf_count }} 份</span>
          </div>
          <div class="status-row">
            <span class="status-label">✂️ 分块</span>
            <span class="status-val">{{ systemStatus.chunk_count }}</span>
          </div>
          <div class="status-row">
            <span class="status-label">🗃️ 向量库</span>
            <el-tag :type="systemStatus.vector_ready ? 'success' : 'warning'" size="small" effect="dark">
              {{ systemStatus.vector_ready ? '就绪' : '未就绪' }}
            </el-tag>
          </div>
          <div class="status-row">
            <span class="status-label">📚 知识库</span>
            <span class="status-val">{{ systemStatus.kb_count }} 个</span>
          </div>
        </div>
        <div v-else style="font-size:12px; color:#546e7a;">加载中...</div>
      </div>

      <div style="border-top:1px solid #2d3e50; margin:6px 0; flex-shrink:0;" />

      <!-- 配置区 -->
      <div style="padding:8px 14px; flex-shrink:0;">
        <div style="font-size:11px; color:#546e7a; font-weight:600; margin-bottom:8px; text-transform:uppercase; letter-spacing:0.5px;">
          检索配置
        </div>
        <!-- 预设选择 -->
        <el-select
          v-model="configStore.activeConfigName"
          size="small"
          style="width:100%; margin-bottom:8px;"
          @change="onConfigChange"
        >
          <el-option label="BASE — 基础" value="base" />
          <el-option label="FAST — 高速" value="fast" />
          <el-option label="PRECISION — 高精度" value="precision" />
          <el-option label="FULL — 完整" value="full" />
        </el-select>

        <!-- 配置快照徽章 -->
        <div v-if="configStore.defaultsLoaded" class="config-badges">
          <el-tooltip v-for="item in configBadges" :key="item.key" :content="item.label">
            <span class="badge" :class="item.on ? 'badge-on' : 'badge-off'">
              {{ item.icon }} {{ item.short }}
            </span>
          </el-tooltip>
        </div>

        <!-- 编辑 + 重置 按钮 -->
        <div style="display:flex; gap:6px; margin-top:8px;">
          <el-button size="small" type="primary" plain @click="drawerOpen = true" style="flex:1;">
            📝 编辑配置
          </el-button>
          <el-button size="small" plain @click="resetConfig"
            :disabled="!configStore.hasOverrides"
            title="恢复预设默认值">
            🔄
          </el-button>
        </div>
        <div v-if="configStore.hasOverrides" style="font-size:11px; color:#e6a23c; margin-top:4px;">
          ⚠️ 已有自定义覆盖
        </div>
      </div>

      <!-- 弹性占位 -->
      <div style="flex:1;" />

      <!-- 用户信息 -->
      <div style="padding:12px 16px; border-top:1px solid #2d3e50; color:#78909c; font-size:13px; display:flex; align-items:center; gap:8px; flex-shrink:0;">
        <el-icon><User /></el-icon>
        <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          {{ authStore.user?.username ?? '...' }}
        </span>
        <el-button text style="color:#78909c; padding:0;" @click="handleLogout">退出</el-button>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-main style="padding:0; overflow:hidden;">
      <router-view />
    </el-main>

    <!-- 配置编辑 Drawer -->
    <ConfigDrawer
      v-model="drawerOpen"
      :config-name="configStore.activeConfigName"
    />
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useConfigStore } from '@/stores/config'
import ConfigDrawer from '@/components/ConfigDrawer.vue'
import http from '@/api/http'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const configStore = useConfigStore()

const drawerOpen = ref(false)
const systemStatus = ref<any>(null)

onMounted(async () => {
  if (authStore.isLoggedIn() && !authStore.user) {
    await authStore.fetchMe()
  }
  await Promise.all([
    configStore.fetchPresetDefaults(),
    fetchSystemStatus(),
  ])
})

async function fetchSystemStatus() {
  try {
    const r = await http.get('/system/status')
    systemStatus.value = r.data
  } catch { /* ignore */ }
}

function onConfigChange() {
  // 切换预设时清除旧覆盖
  configStore.resetOverrides(configStore.activeConfigName)
}

function resetConfig() {
  configStore.resetOverrides(configStore.activeConfigName)
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

// 配置快照徽章
const configBadges = computed(() => {
  const eff = configStore.activeEffective
  return [
    { key: 'parent', icon: '📎', short: '父子块', label: '父子块检索', on: eff.enable_parent_retrieval ?? true },
    { key: 'history', icon: '💬', short: '对话', label: '对话历史', on: eff.enable_history ?? true },
    { key: 'mq', icon: '🔄', short: 'MQ', label: 'MultiQuery扩展', on: eff.enable_multiquery ?? true },
    { key: 'rw', icon: '✏️', short: '改写', label: 'Query改写', on: eff.enable_query_rewrite ?? true },
    { key: 'rerank', icon: '🗳️', short: '重排', label: 'Rerank精排', on: eff.enable_rerank ?? true },
  ]
})

import { ChatDotRound, Files, DataAnalysis, Monitor, User } from '@element-plus/icons-vue'
</script>

<style scoped>
.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  padding: 2px 0;
}
.status-label { color: #78909c; }
.status-val { color: #b0bec5; font-weight: 500; }

.config-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
  cursor: default;
  user-select: none;
}
.badge-on  { background: #1b3a2c; color: #67c23a; }
.badge-off { background: #2d2d2d; color: #546e7a; text-decoration: line-through; }
</style>
