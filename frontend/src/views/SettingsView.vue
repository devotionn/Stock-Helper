<template>
  <div class="page-container">
    <h1 class="page-title">系统设置</h1>

    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在加载设置...</div>
    </div>

    <template v-else>
      <!-- AI接口配置 -->
      <div class="card">
        <h2 class="section-title">AI接口配置</h2>
        <div class="form-group">
          <label class="form-label">API地址</label>
          <input type="text" class="form-input" v-model="form.ai_api_url" placeholder="例如：https://api.example.com/v1" />
        </div>
        <div class="form-group">
          <label class="form-label">API密钥</label>
          <input type="password" class="form-input" v-model="form.ai_api_key" placeholder="输入API密钥" />
        </div>
        <div class="form-group">
          <label class="form-label">模型名称</label>
          <input type="text" class="form-input" v-model="form.ai_model" placeholder="例如：gpt-4" />
        </div>
        <button class="btn btn-primary" :disabled="savingAI" @click="saveAI">
          {{ savingAI ? '保存中...' : '保存AI配置' }}
        </button>
      </div>

      <!-- 显示设置 -->
      <div class="card">
        <h2 class="section-title">显示设置</h2>
        <div class="form-group">
          <label class="form-label">字体大小</label>
          <select class="form-select" v-model="form.font_size">
            <option value="16">16px（较小）</option>
            <option value="18">18px（标准）</option>
            <option value="20">20px（较大）</option>
            <option value="22">22px（大）</option>
            <option value="24">24px（超大）</option>
          </select>
        </div>
        <div class="font-preview">字体预览：股票分析助手</div>
        <button class="btn btn-primary mt-4" :disabled="savingFont" @click="saveFont">
          {{ savingFont ? '保存中...' : '保存显示设置' }}
        </button>
      </div>

      <!-- 备份设置 -->
      <div class="card">
        <h2 class="section-title">备份设置</h2>
        <div class="form-group">
          <label class="form-label">备份位置</label>
          <input type="text" class="form-input" v-model="form.backup_location" placeholder="例如：D:\Backups" />
        </div>
        <button class="btn btn-primary mb-4" :disabled="savingBackupLocation" @click="saveBackupLocation">
          {{ savingBackupLocation ? '保存中...' : '保存备份位置' }}
        </button>

        <button class="btn btn-success btn-lg w-full" :disabled="backingUp" @click="createBackup">
          {{ backingUp ? '正在备份...' : '一键备份' }}
        </button>

        <div v-if="backupResult" class="backup-result">
          <div class="backup-result-title">备份结果</div>
          <div>{{ backupResult.message }}</div>
          <div v-if="backupResult.file_count" class="text-secondary mt-2">
            文件数：{{ backupResult.file_count }} | 大小：{{ formatSize(backupResult.total_size) }}
          </div>
        </div>

        <div class="subsection-title">备份历史</div>
        <button class="btn btn-secondary btn-sm mb-4" @click="loadBackupList">刷新列表</button>
        <div v-if="!backupList.length" class="empty-state">暂无备份记录</div>
        <div v-else class="backup-list">
          <div v-for="b in backupList" :key="b.id" class="backup-item">
            <div class="backup-item-time">{{ formatTime(b.created_at) }}</div>
            <div class="backup-item-meta">
              {{ b.file_count || 0 }} 个文件 | {{ formatSize(b.total_size) }}
            </div>
            <span :class="['status-tag', backupStatusClass(b.status)]">{{ backupStatusText(b.status) }}</span>
          </div>
        </div>

        <div class="subsection-title">恢复备份</div>
        <button class="btn btn-primary" @click="triggerRestore">选择备份文件恢复</button>
        <input
          ref="fileInput"
          type="file"
          accept=".shbackup"
          style="display:none"
          @change="onFileSelected"
        />
      </div>
    </template>

    <!-- 恢复确认弹窗 -->
    <div v-if="showRestoreModal" class="modal-overlay" @click.self="cancelRestore">
      <div class="modal">
        <div class="modal-title">确认恢复</div>
        <div class="modal-body">
          <p class="mb-4">⚠️ 恢复将覆盖当前数据，是否继续？</p>
          <p v-if="restoreFile">备份文件：{{ restoreFile.name }}</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="cancelRestore">取消</button>
          <button class="btn btn-danger" :disabled="restoring" @click="confirmRestore">
            {{ restoring ? '恢复中...' : '确认恢复' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, inject } from 'vue'
import { settingsApi, backupApi } from '../api'

const showToast = inject('toast')

const loading = ref(true)
const form = reactive({
  ai_api_url: '',
  ai_api_key: '',
  ai_model: '',
  backup_location: '',
  font_size: '18',
})

const savingAI = ref(false)
const savingFont = ref(false)
const savingBackupLocation = ref(false)
const backingUp = ref(false)
const backupResult = ref(null)
const backupList = ref([])

const showRestoreModal = ref(false)
const restoreFile = ref(null)
const restoring = ref(false)
const fileInput = ref(null)

async function loadSettings() {
  loading.value = true
  try {
    const { data } = await settingsApi.get()
    form.ai_api_url = data.ai_api_url || ''
    form.ai_api_key = data.ai_api_key || ''
    form.ai_model = data.ai_model || ''
    form.backup_location = data.backup_location || ''
    form.font_size = data.font_size || '18'
    applyFontSize()
  } catch (e) {
    showToast('加载设置失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    loading.value = false
  }
}

async function saveAI() {
  savingAI.value = true
  try {
    await settingsApi.update({
      ai_api_url: form.ai_api_url,
      ai_api_key: form.ai_api_key,
      ai_model: form.ai_model,
    })
    showToast('AI配置保存成功', 'success')
  } catch (e) {
    showToast('保存失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    savingAI.value = false
  }
}

function applyFontSize() {
  document.documentElement.style.setProperty('--font-size-base', form.font_size + 'px')
}

async function saveFont() {
  savingFont.value = true
  try {
    await settingsApi.update({ font_size: form.font_size })
    applyFontSize()
    showToast('显示设置保存成功', 'success')
  } catch (e) {
    showToast('保存失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    savingFont.value = false
  }
}

async function saveBackupLocation() {
  savingBackupLocation.value = true
  try {
    await settingsApi.update({ backup_location: form.backup_location })
    showToast('备份位置已保存', 'success')
  } catch (e) {
    showToast('保存失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    savingBackupLocation.value = false
  }
}

async function createBackup() {
  backingUp.value = true
  backupResult.value = null
  try {
    const { data } = await backupApi.create()
    backupResult.value = data
    showToast(data.message || '备份成功', 'success')
    loadBackupList()
  } catch (e) {
    showToast('备份失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    backingUp.value = false
  }
}

async function loadBackupList() {
  try {
    const { data } = await backupApi.list()
    backupList.value = data || []
  } catch (e) {
    showToast('加载备份列表失败', 'error')
  }
}

function triggerRestore() {
  fileInput.value?.click()
}

function onFileSelected(e) {
  const file = e.target.files[0]
  if (!file) return
  restoreFile.value = file
  showRestoreModal.value = true
  e.target.value = ''
}

function cancelRestore() {
  showRestoreModal.value = false
  restoreFile.value = null
}

async function confirmRestore() {
  if (!restoreFile.value) return
  restoring.value = true
  try {
    const { data } = await backupApi.restore(restoreFile.value)
    showToast(data.message || '恢复成功', 'success')
    showRestoreModal.value = false
    restoreFile.value = null
    loadSettings()
  } catch (e) {
    showToast('恢复失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    restoring.value = false
  }
}

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  if (isNaN(d.getTime())) return dt
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function backupStatusText(status) {
  const map = { completed: '成功', success: '成功', failed: '失败', running: '进行中' }
  return map[status] || status || '未知'
}

function backupStatusClass(status) {
  if (status === 'completed' || status === 'success') return 'status-completed'
  if (status === 'failed') return 'status-failed'
  if (status === 'running') return 'status-running'
  return 'status-pending'
}

onMounted(() => {
  loadSettings()
  loadBackupList()
})
</script>

<style scoped>
.section-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  margin-bottom: 20px;
  color: var(--text);
}

.font-preview {
  font-size: var(--font-size-lg);
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
  color: var(--text);
}

.backup-result {
  background: #e6f4ea;
  border-left: 4px solid var(--success);
  padding: 16px 20px;
  border-radius: 8px;
  margin-top: 20px;
  font-size: var(--font-size-base);
  line-height: 1.8;
}

.backup-result-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--success);
  margin-bottom: 8px;
}

.subsection-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  margin: 28px 0 12px;
  color: var(--text);
}

.backup-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.backup-item {
  display: flex;
  align-items: center;
  gap: 16px;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px 20px;
  flex-wrap: wrap;
}

.backup-item-time {
  font-size: var(--font-size-base);
  font-weight: 600;
}

.backup-item-meta {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  flex: 1;
}

.status-tag {
  display: inline-block;
  padding: 4px 16px;
  border-radius: 20px;
  font-size: 16px;
  font-weight: 600;
}

.status-completed {
  background: #e6f4ea;
  color: var(--success);
}

.status-failed {
  background: #fce8e6;
  color: var(--danger);
}

.status-running {
  background: #e8f0fe;
  color: var(--primary);
}

.status-pending {
  background: #f1f3f4;
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .backup-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>
