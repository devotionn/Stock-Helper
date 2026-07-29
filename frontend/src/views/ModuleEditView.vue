<template>
  <div class="page-container">
    <!-- 顶部工具栏 -->
    <div class="edit-header">
      <button class="btn btn-secondary" @click="goBack">← 返回工作台</button>
      <h1 class="page-title">{{ module.module_name || '模块编辑' }}</h1>
      <span :class="['save-status', saveStatus]">{{ saveStatusText }}</span>
      <button class="btn btn-primary" :disabled="saving || loading" @click="manualSave">保存</button>
    </div>
    <div v-if="module.module_desc" class="module-desc-text">{{ module.module_desc }}</div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在加载模块内容...</div>
    </div>

    <template v-else>
      <!-- 文字录入 -->
      <div class="form-group">
        <label class="form-label">文字内容</label>
        <textarea
          v-model="textContent"
          class="form-textarea edit-textarea"
          placeholder="在此输入或粘贴文字内容..."
        ></textarea>
      </div>

      <!-- 图片管理 -->
      <div class="form-group">
        <label class="form-label">图片（支持上传或直接 Ctrl+V 粘贴截图）</label>
        <div class="upload-row">
          <button class="btn btn-primary" :disabled="uploading" @click="triggerUpload">
            {{ uploading ? '上传中...' : '上传图片' }}
          </button>
          <input
            ref="fileInput"
            type="file"
            accept="image/*"
            multiple
            style="display:none"
            @change="onFileChange"
          />
          <span class="text-secondary">可多选，也可在此页面按 Ctrl+V 粘贴截图</span>
        </div>

        <div v-if="images.length" class="image-grid">
          <div v-for="(img, index) in images" :key="img.id" class="image-item">
            <div class="image-thumb">
              <img
                :src="assetUrl(img.thumbnail_path || img.relative_path)"
                @click="previewImage = img"
                alt="缩略图"
              />
              <button class="delete-btn" title="删除图片" @click.stop="confirmDelete(img)">×</button>
            </div>
            <div class="image-sort">
              <button
                class="btn btn-secondary btn-sm"
                :disabled="index === 0"
                @click="moveImage(index, -1)"
              >↑ 上移</button>
              <button
                class="btn btn-secondary btn-sm"
                :disabled="index === images.length - 1"
                @click="moveImage(index, 1)"
              >↓ 下移</button>
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
          暂无图片，点击上方“上传图片”按钮，或直接按 Ctrl+V 粘贴截图
        </div>
      </div>

      <!-- 底部保存 -->
      <div class="edit-footer">
        <span :class="['save-status', saveStatus]">{{ saveStatusText }}</span>
        <button class="btn btn-primary btn-lg" :disabled="saving" @click="manualSave">保存</button>
      </div>
    </template>

    <!-- 大图查看 -->
    <div v-if="previewImage" class="image-overlay" @click="previewImage = null">
      <img :src="assetUrl(previewImage.relative_path)" alt="大图" />
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
      <div class="modal">
        <div class="modal-title">确认删除</div>
        <div class="modal-body">确定要删除这张图片吗？删除后将无法恢复。</div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="deleteTarget = null">取消</button>
          <button class="btn btn-danger" @click="doDelete">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import { useRouter } from 'vue-router'
import { modulesApi, assetUrl } from '../api'

const props = defineProps({
  id: { type: [String, Number], required: true },
})

const router = useRouter()
const showToast = inject('toast')

const moduleId = computed(() => Number(props.id))

const module = ref({})
const textContent = ref('')
const revision = ref(0)
const images = ref([])

const loading = ref(true)
const saving = ref(false)
const uploading = ref(false)

// 保存状态：saved 已自动保存 / saving 保存中 / unsaved 未保存
const saveStatus = ref('saved')
let lastSavedText = ''

const previewImage = ref(null)
const deleteTarget = ref(null)

const fileInput = ref(null)

const saveStatusText = computed(() => {
  return { saved: '已自动保存', saving: '保存中...', unsaved: '未保存' }[saveStatus.value] || ''
})

// ---- 加载数据 ----
async function loadAll() {
  loading.value = true
  try {
    const [draftRes, imagesRes] = await Promise.all([
      modulesApi.getDraft(moduleId.value),
      modulesApi.getImages(moduleId.value),
    ])
    module.value = draftRes.data
    revision.value = draftRes.data.revision
    lastSavedText = draftRes.data.text_content
    textContent.value = draftRes.data.text_content
    images.value = imagesRes.data
    saveStatus.value = 'saved'
  } catch (e) {
    showToast('加载模块失败', 'error')
  } finally {
    loading.value = false
  }
}

// ---- 自动保存（防抖 5 秒） ----
let autoSaveTimer = null
function scheduleAutoSave() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => doSave(true), 5000)
}

watch(textContent, () => {
  if (loading.value) return
  if (textContent.value === lastSavedText) {
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
  // 内容无变化
  if (textContent.value === lastSavedText) {
    saveStatus.value = 'saved'
    if (!isAuto) showToast('内容无变化', 'warning')
    return
  }
  saving.value = true
  saveStatus.value = 'saving'
  try {
    const { data } = await modulesApi.updateDraft(moduleId.value, textContent.value, revision.value)
    revision.value = data.revision
    lastSavedText = textContent.value
    saveStatus.value = 'saved'
    if (!isAuto) showToast('保存成功', 'success')
  } catch (err) {
    if (err.response && err.response.status === 409) {
      showToast('内容已在另一个页面更新，请刷新', 'error')
      saveStatus.value = 'unsaved'
    } else {
      showToast('保存失败', 'error')
      saveStatus.value = 'unsaved'
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

// ---- 图片上传 ----
function triggerUpload() {
  fileInput.value && fileInput.value.click()
}

async function onFileChange(e) {
  const files = e.target.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
  e.target.value = ''
}

async function uploadFiles(fileList) {
  uploading.value = true
  try {
    for (const file of fileList) {
      try {
        const { data } = await modulesApi.uploadImage(moduleId.value, file)
        images.value.push(data)
      } catch (e) {
        showToast(`图片“${file.name}”上传失败`, 'error')
      }
    }
    showToast('图片上传完成', 'success')
  } finally {
    uploading.value = false
  }
}

// ---- 粘贴截图 ----
function handlePaste(e) {
  const items = e.clipboardData && e.clipboardData.items
  if (!items) return
  const imageFiles = []
  for (const item of items) {
    if (item.type && item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) imageFiles.push(file)
    }
  }
  if (imageFiles.length === 0) return
  e.preventDefault()
  uploadFiles(imageFiles)
}

// ---- 图片说明 ----
async function saveCaption(img) {
  try {
    await modulesApi.updateImageCaption(moduleId.value, img.id, img.caption)
    showToast('图片说明已保存', 'success')
  } catch (e) {
    showToast('图片说明保存失败', 'error')
  }
}

// ---- 图片排序 ----
async function moveImage(index, direction) {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= images.value.length) return
  const arr = images.value
  ;[arr[index], arr[newIndex]] = [arr[newIndex], arr[index]]
  images.value = [...arr]
  try {
    await modulesApi.reorderImages(moduleId.value, images.value.map((i) => i.id))
    showToast('排序已更新', 'success')
  } catch (e) {
    showToast('排序保存失败', 'error')
  }
}

// ---- 删除图片 ----
function confirmDelete(img) {
  deleteTarget.value = img
}

async function doDelete() {
  const img = deleteTarget.value
  deleteTarget.value = null
  if (!img) return
  try {
    await modulesApi.deleteImage(moduleId.value, img.id)
    images.value = images.value.filter((i) => i.id !== img.id)
    showToast('图片已删除', 'success')
  } catch (e) {
    showToast('删除失败', 'error')
  }
}

// ---- 返回 ----
function goBack() {
  router.push('/')
}

// ---- 生命周期 ----
onMounted(() => {
  loadAll()
  window.addEventListener('paste', handlePaste)
})

onBeforeUnmount(() => {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  window.removeEventListener('paste', handlePaste)
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
.edit-header .page-title {
  margin-bottom: 0;
  flex: 1;
  min-width: 200px;
}
.module-desc-text {
  color: var(--text-secondary);
  font-size: var(--font-size-lg);
  margin-bottom: 24px;
}
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
.image-sort .btn {
  flex: 1;
}
.save-status {
  font-size: var(--font-size-lg);
  font-weight: 600;
  white-space: nowrap;
}
.save-status.saved {
  color: var(--success);
}
.save-status.saving {
  color: var(--text-secondary);
}
.save-status.unsaved {
  color: var(--warning);
}
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
