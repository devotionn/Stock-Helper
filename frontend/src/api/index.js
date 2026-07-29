import axios from 'axios'
import { getCurrentRecordDate } from '../dateContext'

const api = axios.create({
  baseURL: '/api',
  timeout: 180000,
})

let sessionToken = null
let tokenPromise = null

async function fetchSessionToken() {
  const res = await axios.get('/api/session')
  sessionToken = res.data.token
  return sessionToken
}

function ensureSessionToken() {
  if (!sessionToken && !tokenPromise) {
    tokenPromise = fetchSessionToken().catch((error) => {
      tokenPromise = null
      throw error
    })
  }
  return tokenPromise
}

api.interceptors.request.use(async (config) => {
  if (!sessionToken) await ensureSessionToken()
  if (sessionToken) config.headers['X-Session-Token'] = sessionToken
  return config
})

export function getSessionToken() {
  return sessionToken
}

function workspaceDate(recordDate) {
  return recordDate || getCurrentRecordDate()
}

export const workspacesApi = {
  get: (recordDate) => api.get(`/workspaces/${workspaceDate(recordDate)}`),
  calendar: (month) => api.get('/workspaces/calendar', { params: { month } }),
  copy: (targetDate, sourceDate, moduleIds, overwrite = false) =>
    api.post(`/workspaces/${targetDate}/copy`, {
      source_date: sourceDate,
      module_ids: moduleIds,
      overwrite,
    }),
}

export const modulesApi = {
  getCards: (recordDate) =>
    workspacesApi.get(recordDate).then((response) => ({ ...response, data: response.data.cards })),
  getDraft: (id, recordDate) => api.get(`/workspaces/${workspaceDate(recordDate)}/modules/${id}`),
  updateDraft: (id, textContent, revision, metadata = {}, recordDate) =>
    api.put(`/workspaces/${workspaceDate(recordDate)}/modules/${id}`, {
      text_content: textContent,
      revision,
      display_title: metadata.displayTitle || '',
      period_start: metadata.periodStart || null,
      period_end: metadata.periodEnd || null,
      status: metadata.status || 'draft',
    }),
  getImages: (id, recordDate) =>
    api.get(`/workspaces/${workspaceDate(recordDate)}/modules/${id}/images`),
  uploadImage: (id, file, recordDate) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/workspaces/${workspaceDate(recordDate)}/modules/${id}/images`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  deleteImage: (moduleId, assetId, recordDate) =>
    api.delete(`/workspaces/${workspaceDate(recordDate)}/modules/${moduleId}/images/${assetId}`),
  updateImageCaption: (moduleId, assetId, caption, recordDate) =>
    api.put(`/workspaces/${workspaceDate(recordDate)}/modules/${moduleId}/images/${assetId}`, {
      caption,
    }),
  reorderImages: (moduleId, assetIds, recordDate) =>
    api.put(`/workspaces/${workspaceDate(recordDate)}/modules/${moduleId}/images/reorder`, assetIds),
  saveVersion: (id, note = '') => api.post(`/modules/${id}/versions`, { note }),
  listVersions: (id) => api.get(`/modules/${id}/versions`),
}

export const combinationsApi = {
  list: () => api.get('/combinations'),
  create: (name, moduleIds) => api.post('/combinations', { name, module_ids: moduleIds }),
  update: (id, name, moduleIds) => api.put(`/combinations/${id}`, { name, module_ids: moduleIds }),
  delete: (id) => api.delete(`/combinations/${id}`),
}

export const analysisApi = {
  create: (moduleIds, analysisRequest = '', combinationName = '', recordDate) =>
    api.post('/analysis', {
      module_ids: moduleIds,
      analysis_request: analysisRequest,
      combination_name: combinationName,
      record_date: workspaceDate(recordDate),
    }),
  get: (id) => api.get(`/analysis/${id}`),
  getDetail: (id) => api.get(`/analysis/${id}/detail`),
  saveToModule: (analysisId, moduleId, content) =>
    api.post('/analysis/save-to-module', {
      analysis_id: analysisId,
      module_id: moduleId,
      content,
    }),
  updateReview: (id, reviewContent) =>
    api.put(`/analysis/${id}/review`, { review_content: reviewContent }),
}

export const historyApi = {
  list: (params) => api.get('/history', { params }),
  getDetail: (id) => api.get(`/history/${id}/detail`),
  updateNote: (id, note) => api.put(`/history/${id}/note`, { note }),
  delete: (id) => api.delete(`/history/${id}`, { params: { confirm: '确认删除' } }),
}

export const settingsApi = {
  get: () => api.get('/settings'),
  update: (data) => api.put('/settings', data),
}

export const backupApi = {
  create: () => api.post('/backup'),
  list: () => api.get('/backup'),
  restore: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/backup/restore', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

export const assetUrl = (relativePath) => `/uploads/${relativePath}`
export default api
