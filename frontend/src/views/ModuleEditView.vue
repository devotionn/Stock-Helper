<template>
  <div class="page-container">
    <div class="edit-header">
      <button class="btn btn-secondary" @click="goBack">← 返回工作台</button>
      <div class="edit-heading">
        <h1 class="page-title">{{ module.module_name || '模块编辑' }}</h1>
        <div class="record-date-badge">{{ formattedRecordDate }}</div>
      </div>
      <span :class="['save-status', saveStatus]">{{ saveStatusText }}</span>
      <button class="btn btn-primary" :disabled="saving || loading" @click="manualSave">保存</button>
    </div>
    <div v-if="module.module_desc" class="module-desc-text">{{ module.module_desc }}</div>

    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在加载模块内容...</div>
    </div>

    <template v-else>
      <div v-if="isStockModule" class="form-group metadata-card">
        <label class="form-label">股票名称 / 代码</label>
        <input
          v-model="displayTitle"
          class="form-input"
          placeholder="例如：宁德时代 300750"
        />
        <div class="field-hint">该名称只属于 {{ recordDate }}，不会影响其他日期。</div>
      </div>

      <div v-if="moduleId === 0" class="form-group metadata-card">
        <label class="form-label">策略有效期</label>
        <div class="period-row">
          <input v-model="periodStart" type="date" class="form-input" />
          <span>至</span>
          <input v-model="periodEnd" type="date" class="form-input" />
        </div>
        <div class="field-hint">用于说明本周策略适用范围，不改变当前投研日期。</div>
      </div>

      <div class="form-group">
        <label class="form-label">文字内容</label>
        <textarea
          v-model="textContent"
          class="form-textarea edit-textarea"
          placeholder="在此输入或粘贴文字内容..."
        ></textarea>
      </div>

      <div class="form-group">
        <label class="form-label">图片（支持上传或直接{{ pasteTip }}）</label>
        <div class="upload-row">
          <button class="btn btn-primary" :disabled="uploading" @click="triggerUpload">
            {{ uploading ? '上传中...' : '上传图片' }}
          </button>
          <input
            ref="fileInput"
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif,image/bmp"
            multiple
            style="display: none"
            @change="onFileChange"
          />
          <span class="text-secondary">支持 JPG/PNG/WebP/GIF/BMP，可多选，也可在此页面{{ pasteTip }}</span>
        </div>

        <div v-if="images.length" class="image-grid">
          <div v-for="(img, index) in images" :key="img.id" class="image-item">
            <div class="image-thumb">
              <img
                :src="assetUrl(img.thumbnail_path || img.relative_path)"
                alt="缩略图"
                @click="previewImage = img"
              />
              <button class="delete-btn" title="删除图片" @click.stop="confirmDelete(img)">×</button>
            </div>
            <div class="image-sort">
              <button class="btn btn-secondary btn-sm" :disabled="index === 0" @click="moveImage(index, -1)">
                ↑ 上移
              </button>
              <button
                class="btn btn-secondary btn-sm"
                :disabled="index === images.length - 1"
                @click="moveImage(index, 1)"
              >
                ↓ 下移
              </button>
            </div>
            <input
              v-model="img.caption"
              class="form-input image-caption"
              placeholder="图片说明"
              @change="saveCaption(img)"
            />
          </div>
        </div>
        <div v-else class="empty-state">
          暂无图片，点击上方“上传图片”按钮，或直接{{ pasteTip }}
        </div>
      </div>

      <div class="edit-footer">
        <span :class="['save-status', saveStatus]">{{ saveStatusText }}</span>
        <button class="btn btn-primary btn-lg" :disabled="saving" @click="manualSave">保存</button>
      </div>
    </template>

    <div v-if="previewImage" class="image-overlay" @click="previewImage = null">
      <img :src="assetUrl(previewImage.relative_path)" alt="大图" />
    </div>

    <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
      <div class="modal">
        <div class="modal-title">确认删除</div>
        <div class="modal-body">确定要删除这张图片吗？删除后将从 {{ recordDate }} 的当前模块移除。</div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="deleteTarget = null">取消</button>
          <button class="btn btn-danger" @click="doDelete">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { assetUrl, getSessionToken, modulesApi } from '../api'
import {
  currentRecordDate,
  formatRecordDate,
  isValidRecordDate,
  setCurrentRecordDate,
} from '../dateContext'

const props = defineProps({
  id: { type: [String, Number], required: true },
})

const router = useRouter()
const route = useRoute()
const showToast = inject('toast')
const isMac = navigator.platform.toUpperCase().includes('MAC')
const pasteTip = isMac ? '按 Command + V 粘贴截图' : '按 Ctrl + V 粘贴截图'
const moduleId = computed(() => Number(props.id))
const isStockModule = computed(() => moduleId.value >= 1 && moduleId.value <= 4)
const recordDate = currentRecordDate
const formattedRecordDate = computed(() => formatRecordDate(recordDate.value))

const module = ref({})
const textContent = ref('')
const displayTitle = ref('')
const periodStart = ref('')
const periodEnd = ref('')
const revision = ref(0)
const images = ref([])
const loading = ref(true)
const saving = ref(false)
const uploading = ref(false)
const saveStatus = ref('saved')
const previewImage = ref(null)
const deleteTarget = ref(null)
const fileInput = ref(null)
let autoSaveTimer = null
let lastSavedState = ''

const saveStatusText = computed(() => {
  return { saved: '已自动保存', saving: '保存中...', unsaved: '未保存' }[saveStatus.value] || ''
})

function currentState() {
  return JSON.stringify({
    textContent: textContent.value,
    displayTitle: displayTitle.value,
    periodStart: periodStart.value,
    periodEnd: periodEnd.value,
  })
}

async function loadAll() {
  loading.value = true
  try {
    const [draftResponse, imagesResponse] = await Promise.all([
      modulesApi.getDraft(moduleId.value, recordDate.value),
      modulesApi.getImages(moduleId.value, recordDate.value),
    ])
    module.value = draftResponse.data
    revision.value = draftResponse.data.revision
    textContent.value = draftResponse.data.text_content || ''
    displayTitle.value = draftResponse.data.display_title || ''
    periodStart.value = draftResponse.data.period_start || ''
    periodEnd.value = draftResponse.data.period_end || ''
    images.value = imagesResponse.data
    lastSavedState = currentState()
    saveStatus.value = 'saved'
  } catch (error) {
    showToast(error.response?.data?.detail || '加载模块失败', 'error')
  } finally {
    loading.value = false
  }
}

function scheduleAutoSave() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => doSave(true), 1200)
}

watch([textContent, displayTitle, periodStart, periodEnd], () => {
  if (loading.value) return
  if (currentState() === lastSavedState) {
    saveStatus.value = 'saved'
    return
  }
  saveStatus.value = 'unsaved'
  scheduleAutoSave()
})

async function doSave(isAuto = false) {
  if (saving.value) {
    if (isAuto) scheduleAutoSave()
    return
  }
  if (currentState() === lastSavedState) {
    saveStatus.value = 'saved'
    if (!isAuto) showToast('内容无变化', 'warning')
    return
  }

  saving.value = true
  saveStatus.value = 'saving'
  try {
    const { data } = await modulesApi.updateDraft(
      moduleId.value,
      textContent.value,
      revision.value,
      {
        displayTitle: displayTitle.value,
        periodStart: periodStart.value,
        periodEnd: periodEnd.value,
      },
      recordDate.value,
    )
    revision.value = data.revision
    lastSavedState = currentState()
    saveStatus.value = 'saved'
    if (!isAuto) showToast('保存成功', 'success')
  } catch (error) {
    saveStatus.value = 'unsaved'
    if (error.response?.status === 409) {
      showToast('内容已在另一个页面更新，请刷新', 'error')
    } else {
      showToast(error.response?.data?.detail || '保存失败', 'error')
      if (isAuto) scheduleAutoSave()
    }
  } finally {
    saving.value = false
  }
}

function manualSave() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  doSave(false)
}

function triggerUpload() {
  fileInput.value?.click()
}

async function onFileChange(event) {
  const files = event.target.files
  if (!files?.length) return
  await uploadFiles(Array.from(files))
  event.target.value = ''
}

async function uploadFiles(fileList) {
  uploading.value = true
  let successCount = 0
  const failedFiles = []
  try {
    for (const file of fileList) {
      try {
        const { data } = await modulesApi.uploadImage(moduleId.value, file, recordDate.value)
        if (!images.value.some((image) => image.id === data.id)) images.value.push(data)
        successCount += 1
      } catch {
        failedFiles.push(file.name)
      }
    }
    let message = `成功上传${successCount}张`
    if (failedFiles.length) message += `，失败${failedFiles.length}张：${failedFiles.join('、')}`
    showToast(message, failedFiles.length ? 'warning' : 'success')
  } finally {
    uploading.value = false
  }
}

function handlePaste(event) {
  const items = event.clipboardData?.items
  if (!items) return
  const files = []
  for (const item of items) {
    if (item.type?.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }
  if (!files.length) return
  event.preventDefault()
  uploadFiles(files)
}

async function saveCaption(image) {
  try {
    await modulesApi.updateImageCaption(moduleId.value, image.id, image.caption, recordDate.value)
    showToast('图片说明已保存', 'success')
  } catch {
    showToast('图片说明保存失败', 'error')
  }
}

async function moveImage(index, direction) {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= images.value.length) return
  const reordered = [...images.value]
  ;[reordered[index], reordered[newIndex]] = [reordered[newIndex], reordered[index]]
  images.value = reordered
  try {
    await modulesApi.reorderImages(
      moduleId.value,
      images.value.map((image) => image.id),
      recordDate.value,
    )
    showToast('排序已更新', 'success')
  } catch {
    showToast('排序保存失败，请刷新后重试', 'error')
    await loadAll()
  }
}

function confirmDelete(image) {
  deleteTarget.value = image
}

async function doDelete() {
  const image = deleteTarget.value
  deleteTarget.value = null
  if (!image) return
  try {
    await modulesApi.deleteImage(moduleId.value, image.id, recordDate.value)
    images.value = images.value.filter((item) => item.id !== image.id)
    showToast('图片已删除', 'success')
  } catch {
    showToast('删除失败', 'error')
  }
}

function goBack() {
  router.push({ path: '/', query: { date: recordDate.value } })
}

function handleBeforeUnload() {
  if (currentState() === lastSavedState || saving.value) return
  const token = getSessionToken()
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['X-Session-Token'] = token
  try {
    fetch(`/api/workspaces/${recordDate.value}/modules/${moduleId.value}`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({
        text_content: textContent.value,
        revision: revision.value,
        display_title: displayTitle.value,
        period_start: periodStart.value || null,
        period_end: periodEnd.value || null,
        status: 'draft',
      }),
      keepalive: true,
    })
  } catch {
    // 页面正在关闭，错误无法再向用户展示。
  }
}

onMounted(() => {
  const queryDate = String(route.query.date || '')
  if (isValidRecordDate(queryDate)) setCurrentRecordDate(queryDate)
  loadAll()
  window.addEventListener('paste', handlePaste)
  window.addEventListener('beforeunload', handleBeforeUnload)
})

onBeforeUnmount(() => {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  window.removeEventListener('paste', handlePaste)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  if (currentState() !== lastSavedState && !saving.value) doSave(true)
})
</script>

<style scoped>
.edit-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.edit-heading {
  flex: 1;
  min-width: 230px;
}
.edit-heading .page-title { margin-bottom: 4px; }
.record-date-badge {
  color: var(--primary);
  font-size: 17px;
  font-weight: 700;
}
.module-desc-text {
  color: var(--text-secondary);
  font-size: var(--font-size-lg);
  margin-bottom: 24px;
}
.metadata-card {
  background: #f7f9fc;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px;
}
.field-hint {
  color: var(--text-secondary);
  font-size: 15px;
  margin-top: 8px;
}
.period-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.period-row .form-input { max-width: 240px; }
.edit-textarea {
  font-size: 18px;
  min-height: 280px;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.image-item {
  display: flex;
  flex-direction: column;
  width: 150px;
}
.image-caption {
  margin-top: 8px;
  font-size: 16px;
  padding: 8px 10px;
}
.image-sort {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}
.image-sort .btn { flex: 1; }
.save-status {
  font-size: var(--font-size-lg);
  font-weight: 600;
  white-space: nowrap;
}
.save-status.saved { color: var(--success); }
.save-status.saving { color: var(--text-secondary); }
.save-status.unsaved { color: var(--warning); }
.edit-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 24px;
  padding-top: 24px;
  border-top: 2px solid var(--border);
}
</style>
