import { defineStore } from 'pinia'
import { ref } from 'vue'
import { kbApi, type KB } from '@/api/kb'

export const useKBStore = defineStore('kb', () => {
  const list = ref<KB[]>([])
  const current = ref<KB | null>(null)

  async function fetchList() {
    const res = await kbApi.list()
    list.value = res.data
  }

  async function fetchOne(id: string) {
    const res = await kbApi.get(id)
    current.value = res.data
    return res.data
  }

  function setCurrent(kb: KB) {
    current.value = kb
  }

  return { list, current, fetchList, fetchOne, setCurrent }
})
