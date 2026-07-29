import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 180000, // AI分析可能需要较长时间
})

// ---- 模块 ----
export const modulesApi = {
  getCards: () => api.get('/modules'),
  getDraft: (id) => api.get(`/modules/${id}`),
  updateDraft: (id, textContent, revision) => api.put(`/modules/${id}`, { text_content: textContent, revision }),
  getImages: (id) => api.get(`/modules/${id}/images`),
  uploadImage: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`/modules/${id}/images`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  deleteImage: (moduleId, assetId) => api.delete(`/modules/${moduleId}/images/${assetId}`),
  updateImageCaption: (moduleId, assetId, caption) =>
    api.put(`/modules/${moduleId}/images/${assetId}`, { caption }),
  reorderImages: (moduleId, assetIds) => api.put(`/modules/${moduleId}/images/reorder`, assetIds),
  saveVersion: (id, note = '') => api.post(`/modules/${id}/versions`, { note }),
  listVersions: (id) => api.get(`/modules/${id}/versions`),
}

// ---- 常用组合 ----
export const combinationsApi = {
  list: () => api.get('/combinations'),
  create: (name, moduleIds) => api.post('/combinations', { name, module_ids: moduleIds }),
  update: (id, name, moduleIds) => api.put(`/combinations/${id}`, { name, module_ids: moduleIds }),
  delete: (id) => api.delete(`/combinations/${id}`),
}

// ---- 分析 ----
export const analysisApi = {
  create: (moduleIds, analysisRequest = '', combinationName = '') =>
    api.post('/analysis', { module_ids: moduleIds, analysis_request: analysisRequest, combination_name: combinationName }),
  get: (id) => api.get(`/analysis/${id}`),
  getDetail: (id) => api.get(`/analysis/${id}/detail`),
  saveToModule: (analysisId, moduleId, content) =>
    api.post('/analysis/save-to-module', { analysis_id: analysisId, module_id: moduleId, content }),
}

// ---- 历史记录 ----
export const historyApi = {
  list: (params) => api.get('/history', { params }),
  getDetail: (id) => api.get(`/history/${id}/detail`),
  updateNote: (id, note) => api.put(`/history/${id}/note`, { note }),
  delete: (id) => api.delete(`/history/${id}`, { params: { confirm: '确认删除' } }),
}

// ---- 设置 ----
export const settingsApi = {
  get: () => api.get('/settings'),
  update: (data) => api.put('/settings', data),
}

// ---- 备份 ----
export const backupApi = {
  create: () => api.post('/backup'),
  list: () => api.get('/backup'),
  restore: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post('/backup/restore', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}

export const assetUrl = (relativePath) => `/uploads/${relativePath}`

export default api
