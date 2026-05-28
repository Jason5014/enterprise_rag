<template>
  <router-view v-if="route.meta.public" />
  <el-container v-else style="height: 100vh;">
    <!-- 左侧导航 -->
    <el-aside width="200px" style="background:#1a2332; display:flex; flex-direction:column;">
      <div style="padding:20px 16px 12px; color:#fff; font-size:16px; font-weight:600; letter-spacing:0.5px;">
        🧠 企业知识库
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#1a2332"
        text-color="#b0bec5"
        active-text-color="#64b5f6"
        style="border:none; flex:1;"
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
      <!-- 用户信息 -->
      <div style="padding:12px 16px; border-top:1px solid #2d3e50; color:#78909c; font-size:13px; display:flex; align-items:center; gap:8px;">
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
  </el-container>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

onMounted(async () => {
  if (authStore.isLoggedIn() && !authStore.user) {
    await authStore.fetchMe()
  }
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>
