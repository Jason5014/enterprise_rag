import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import http from '@/api/http'

export interface RetrievalOverrides {
  chunk_size?: number
  chunk_overlap?: number
  top_k_retrieval?: number
  enable_parent_retrieval?: boolean
  enable_history?: boolean
  enable_multiquery?: boolean
  enable_query_rewrite?: boolean
  enable_rerank?: boolean
  rerank_top_k?: number
  use_jina_reranker?: boolean
  fusion_method?: string
  bm25_weight?: number
  rrf_k?: number
}

export type ConfigName = 'base' | 'fast' | 'precision' | 'full' | string

export const CONFIG_LABELS: Record<string, string> = {
  base:      'BASE — 基础混合检索',
  fast:      'FAST — 高速（关闭父子块/重排）',
  precision: 'PRECISION — 高精度（全功能）',
  full:      'FULL — 完整功能+日志',
}

export const useConfigStore = defineStore('config', () => {
  /** 全局当前选中的配置预设名 */
  const activeConfigName = ref<ConfigName>('base')

  /** 各预设的默认参数（从后端加载一次） */
  const presetDefaults = ref<Record<string, RetrievalOverrides>>({})

  /** 各预设的运行时覆盖（前端 session 级别） */
  const overrides = ref<Record<string, RetrievalOverrides>>({})

  /** 是否已加载预设默认值 */
  const defaultsLoaded = ref(false)

  /** 获取某预设的覆盖参数 */
  function getOverrides(name: ConfigName): RetrievalOverrides {
    return overrides.value[name] ?? {}
  }

  /** 保存某预设的覆盖参数 */
  function setOverrides(name: ConfigName, patch: RetrievalOverrides) {
    overrides.value[name] = { ...patch }
  }

  /** 清除某预设的覆盖，恢复默认 */
  function resetOverrides(name: ConfigName) {
    delete overrides.value[name]
  }

  /** 获取某预设实际生效的参数（默认 + 覆盖叠加） */
  function getEffective(name: ConfigName): RetrievalOverrides {
    return { ...(presetDefaults.value[name] ?? {}), ...(overrides.value[name] ?? {}) }
  }

  /** 当前生效参数 */
  const activeEffective = computed(() => getEffective(activeConfigName.value))

  /** 当前是否有覆盖 */
  const hasOverrides = computed(() => {
    const ov = overrides.value[activeConfigName.value]
    return ov != null && Object.keys(ov).length > 0
  })

  /** 从后端加载预设默认值 */
  async function fetchPresetDefaults() {
    try {
      const r = await http.get('/config/presets')
      presetDefaults.value = r.data
      defaultsLoaded.value = true
    } catch { /* ignore */ }
  }

  /** 获取序列化的覆盖（用于传给 API）；若无覆盖返回 undefined */
  function getOverridesJson(name?: ConfigName): string | undefined {
    const n = name ?? activeConfigName.value
    const ov = overrides.value[n]
    if (!ov || Object.keys(ov).length === 0) return undefined
    return JSON.stringify(ov)
  }

  return {
    activeConfigName,
    presetDefaults,
    overrides,
    defaultsLoaded,
    activeEffective,
    hasOverrides,
    getOverrides,
    setOverrides,
    resetOverrides,
    getEffective,
    fetchPresetDefaults,
    getOverridesJson,
  }
})
