import http from './http'

export interface KB {
  kb_id: string; name: string; description: string; config_name: string
  status: string; doc_count: number; chunk_count: number
  owner_id?: string; created_at: string; updated_at: string
}

export interface Doc {
  doc_id: string; kb_id: string; filename: string; file_type: string
  file_size: number; upload_time: string; parse_status: string
  parse_error?: string; chunk_count: number
}

export interface Job {
  job_id: string; kb_id: string; job_type: string; status: string
  progress: number; stage_msg?: string; started_at?: string
  finished_at?: string; error_msg?: string; stats_json?: string
}

export const kbApi = {
  list: () => http.get<KB[]>('/kb/'),
  create: (data: { name: string; description?: string; config_name?: string }) =>
    http.post<KB>('/kb/', data),
  get: (id: string) => http.get<KB>(`/kb/${id}`),
  update: (id: string, data: Partial<KB>) => http.patch<KB>(`/kb/${id}`, data),
  delete: (id: string) => http.delete(`/kb/${id}?confirm=true`),

  // files
  uploadFile: (kbId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post<Doc>(`/kb/${kbId}/files`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  listFiles: (kbId: string) => http.get<Doc[]>(`/kb/${kbId}/files`),
  deleteFile: (kbId: string, docId: string) =>
    http.delete(`/kb/${kbId}/files/${docId}`),

  // jobs
  parse: (kbId: string) => http.post<Job>(`/kb/${kbId}/parse`),
  index: (kbId: string) => http.post<Job>(`/kb/${kbId}/index`),
  process: (kbId: string) => http.post<Job>(`/kb/${kbId}/process`),
  listJobs: (kbId: string) => http.get<Job[]>(`/kb/${kbId}/jobs`),
  getJob: (jobId: string) => http.get<Job>(`/kb/jobs/${jobId}`),
}
