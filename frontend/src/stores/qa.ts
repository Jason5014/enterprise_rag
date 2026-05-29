import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface BadForm {
  error_type: string
  correct_answer: string
  comment: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  analysis?: string
  pages?: number[]
  loading?: boolean
  warnings?: string[]
  feedbackDone?: boolean
  showBadForm?: boolean
  badForm?: BadForm
}

export const useQAStore = defineStore('qa', () => {
  const messages = ref<Message[]>([])
  const activeKBId = ref<string | null>(null)

  function addMessage(msg: Message) {
    messages.value.push(msg)
  }

  function updateLast(patch: Partial<Message>) {
    const last = messages.value[messages.value.length - 1]
    if (last) Object.assign(last, patch)
  }

  function updateAt(idx: number, patch: Partial<Message>) {
    const msg = messages.value[idx]
    if (msg) Object.assign(msg, patch)
  }

  function clearHistory() {
    messages.value = []
  }

  function setKB(id: string | null) {
    activeKBId.value = id
  }

  return { messages, activeKBId, addMessage, updateLast, updateAt, clearHistory, setKB }
})
