import http from './http'

export interface QAResponse {
  query: string; final_answer: string; step_by_step_analysis: string
  reasoning_summary: string; relevant_pages: number[]; used_parent_chunks: string[]
}

export interface FeedbackData {
  query: string
  answer: string
  feedback: string        // "good" | "bad"
  comment?: string
  kb_id?: string
  config_name?: string
  pages?: number[]
  error_type?: string
  correct_answer?: string
}

export const qaApi = {
  ask: (query: string, kbId?: string) =>
    http.post<QAResponse>('/qa/ask', { query, kb_id: kbId }),

  feedback: (data: FeedbackData) =>
    http.post('/qa/feedback', data),

  clearHistory: (kbId?: string) =>
    http.delete('/qa/history', { params: { kb_id: kbId } }),
}

/** 创建 SSE 流式问答连接，返回 EventSource */
export function createQAStream(query: string, kbId?: string, configName = 'base'): EventSource {
  const token = localStorage.getItem('token') ?? ''
  const params = new URLSearchParams({ q: query, config_name: configName })
  if (kbId) params.append('kb_id', kbId)
  params.append('token', token)
  return new EventSource(`/api/qa/stream?${params.toString()}`)
}
