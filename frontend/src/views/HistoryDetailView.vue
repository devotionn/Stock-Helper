<template>
  <div class="page-container">
    <!-- 顶部操作栏 -->
    <div class="detail-toolbar">
      <button class="btn btn-secondary" @click="goBack">← 返回列表</button>
      <div class="toolbar-right">
        <button class="btn btn-primary" @click="reAnalyze">再次分析</button>
        <button class="btn btn-danger" @click="showDeleteModal = true">删除</button>
      </div>
    </div>

    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在加载详情...</div>
    </div>

    <template v-else-if="analysis">
      <!-- 分析信息 -->
      <div class="card">
        <h2 class="section-title">分析信息</h2>
        <div class="info-row">
          <span class="info-label">分析时间：</span>
          <span>{{ formatTime(analysis.created_at) }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">状态：</span>
          <span :class="['status-tag', statusClass(analysis.status)]">{{ statusText(analysis.status) }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">模块组合：</span>
          <div class="module-order">
            <span v-for="(mid, idx) in analysis.combination" :key="idx" class="module-chip">
              <span class="module-chip-num">{{ idx + 1 }}</span>
              {{ moduleName(mid) }}
            </span>
          </div>
        </div>
        <div class="info-row">
          <span class="info-label">分析要求：</span>
          <span>{{ analysis.analysis_request || '无' }}</span>
        </div>
        <div v-if="analysis.error_message" class="error-message">
          错误信息：{{ analysis.error_message }}
        </div>
      </div>

      <!-- 模块快照 -->
      <div class="card">
        <h2 class="section-title">模块内容快照</h2>
        <div v-if="!sortedSnapshots.length" class="empty-state">暂无模块快照</div>
        <div v-for="snap in sortedSnapshots" :key="snap.order_index" class="snapshot-item">
          <div class="snapshot-header">
            <span class="snapshot-order">{{ snap.order_index + 1 }}</span>
            <span class="snapshot-name">{{ snap.module_name }}</span>
          </div>
          <div v-if="snap.text_content" class="snapshot-text">{{ snap.text_content }}</div>
          <div v-if="snap.images && snap.images.length" class="image-grid">
            <div
              v-for="(img, i) in snap.images"
              :key="i"
              class="image-thumb"
              @click="previewImage = assetUrl(img.relative_path)"
            >
              <img :src="assetUrl(img.thumbnail_path || img.relative_path)" :alt="snap.module_name" />
            </div>
          </div>
        </div>
      </div>

      <!-- AI分析结果 -->
      <div v-if="analysisSections.length" class="card">
        <h2 class="section-title">AI分析结果</h2>
        <div v-for="(section, i) in analysisSections" :key="i" class="analysis-section">
          <div class="analysis-section-title">{{ section.title }}</div>
          <div class="analysis-section-content">{{ section.content }}</div>
        </div>
      </div>

      <div v-else-if="analysis.raw_result" class="card">
        <h2 class="section-title">AI分析结果</h2>
        <div class="analysis-section">
          <div class="analysis-section-content">{{ analysis.raw_result }}</div>
        </div>
      </div>

      <!-- 免责声明 -->
      <div class="analysis-warning">⚠️ 本分析仅供参考，不构成投资建议</div>

      <!-- 客户备注 -->
      <div class="card">
        <h2 class="section-title">客户备注</h2>
        <div v-if="notes.length" class="notes-list">
          <div v-for="note in notes" :key="note.id" class="note-item">
            <div class="note-text">{{ note.note }}</div>
            <div class="note-time">{{ formatTime(note.created_at) }}</div>
          </div>
        </div>
        <div v-else class="text-secondary mb-4">暂无备注</div>
        <div class="form-group">
          <label class="form-label">添加/修改备注</label>
          <textarea class="form-textarea" v-model="noteText" placeholder="输入备注内容..."></textarea>
        </div>
        <button class="btn btn-primary" :disabled="savingNote" @click="saveNote">
          {{ savingNote ? '保存中...' : '保存备注' }}
        </button>
      </div>
    </template>

    <div v-else class="empty-state">未找到该历史记录</div>

    <!-- 图片预览 -->
    <div v-if="previewImage" class="image-overlay" @click="previewImage = null">
      <img :src="previewImage" alt="预览" />
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteModal" class="modal-overlay" @click.self="cancelDelete">
      <div class="modal">
        <div class="modal-title">确认删除</div>
        <div class="modal-body">
          <p class="mb-4">⚠️ 删除后将无法恢复，确定要删除这条历史记录吗？</p>
          <p>请输入 <strong>确认删除</strong> 以继续：</p>
          <input class="form-input" v-model="deleteConfirmText" placeholder="确认删除" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="cancelDelete">取消</button>
          <button
            class="btn btn-danger"
            :disabled="deleteConfirmText !== '确认删除' || deleting"
            @click="confirmDelete"
          >
            {{ deleting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { historyApi, assetUrl } from '../api'

const router = useRouter()
const route = useRoute()
const showToast = inject('toast')

const id = route.params.id

const MODULES = [
  { id: 0, name: '一周策略' },
  { id: 1, name: '股票1' },
  { id: 2, name: '股票2' },
  { id: 3, name: '股票3' },
  { id: 4, name: '股票4' },
  { id: 5, name: '技术派观点' },
  { id: 6, name: '钱说观点' },
  { id: 7, name: '大盘走势' },
  { id: 8, name: '反向操作' },
  { id: 9, name: 'AI复盘' },
  { id: 10, name: '行业板块' },
  { id: 11, name: '操作建议' },
]

const loading = ref(true)
const analysis = ref(null)
const snapshots = ref([])
const notes = ref([])

const previewImage = ref(null)
const noteText = ref('')
const savingNote = ref(false)

const showDeleteModal = ref(false)
const deleteConfirmText = ref('')
const deleting = ref(false)

const sortedSnapshots = computed(() => {
  return [...snapshots.value].sort((a, b) => a.order_index - b.order_index)
})

const analysisSections = computed(() => {
  if (!analysis.value || !analysis.value.result_json) return []
  try {
    const data = typeof analysis.value.result_json === 'string'
      ? JSON.parse(analysis.value.result_json)
      : analysis.value.result_json
    const keys = ['信息汇总', '一致观点', '冲突观点', '关键判断', '风险提示', '信息不足之处', '操作参考建议']
    return keys.map(k => ({ title: k, content: data[k] || '' })).filter(s => s.content)
  } catch (e) {
    return []
  }
})

function moduleName(mid) {
  const m = MODULES.find(x => x.id === mid)
  return m ? m.name : `模块${mid}`
}

async function fetchDetail() {
  loading.value = true
  try {
    const { data } = await historyApi.getDetail(id)
    analysis.value = data.analysis
    snapshots.value = data.snapshots || []
    notes.value = data.notes || []
    if (notes.value.length) {
      noteText.value = notes.value[0].note
    }
  } catch (e) {
    showToast('加载详情失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    loading.value = false
  }
}

async function saveNote() {
  if (savingNote.value) return
  savingNote.value = true
  try {
    await historyApi.updateNote(id, noteText.value)
    showToast('备注保存成功', 'success')
    await fetchDetail()
  } catch (e) {
    showToast('保存失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    savingNote.value = false
  }
}

function reAnalyze() {
  if (analysis.value && analysis.value.combination && analysis.value.combination.length) {
    router.push({ path: '/analysis', query: { combination: analysis.value.combination.join(',') } })
  } else {
    router.push('/analysis')
  }
}

function goBack() {
  router.push('/history')
}

function cancelDelete() {
  showDeleteModal.value = false
  deleteConfirmText.value = ''
}

async function confirmDelete() {
  deleting.value = true
  try {
    await historyApi.delete(id)
    showToast('删除成功', 'success')
    router.push('/history')
  } catch (e) {
    showToast('删除失败：' + (e.response?.data?.message || e.message), 'error')
  } finally {
    deleting.value = false
  }
}

function formatTime(dt) {
  if (!dt) return ''
  const d = new Date(dt)
  if (isNaN(d.getTime())) return dt
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function statusText(status) {
  const map = { completed: '已完成', failed: '失败', running: '进行中', pending: '等待中' }
  return map[status] || status || '未知'
}

function statusClass(status) {
  const map = { completed: 'status-completed', failed: 'status-failed', running: 'status-running', pending: 'status-pending' }
  return map[status] || 'status-pending'
}

onMounted(() => {
  fetchDetail()
})
</script>

<style scoped>
.detail-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-right {
  display: flex;
  gap: 12px;
}

.section-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  margin-bottom: 20px;
  color: var(--text);
}

.info-row {
  display: flex;
  align-items: flex-start;
  font-size: var(--font-size-lg);
  line-height: 1.8;
  margin-bottom: 12px;
}

.info-label {
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
  flex-shrink: 0;
}

.module-order {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.module-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: #e8f0fe;
  color: var(--primary);
  padding: 6px 14px;
  border-radius: 20px;
  font-size: var(--font-size-base);
  font-weight: 600;
}

.module-chip-num {
  background: var(--primary);
  color: #fff;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
}

.error-message {
  background: #fce8e6;
  color: var(--danger);
  padding: 12px 16px;
  border-radius: 8px;
  margin-top: 12px;
  font-size: var(--font-size-base);
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

.snapshot-item {
  border: 2px solid var(--border);
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 20px;
}

.snapshot-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.snapshot-order {
  background: var(--primary);
  color: #fff;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 18px;
  flex-shrink: 0;
}

.snapshot-name {
  font-size: var(--font-size-lg);
  font-weight: 700;
}

.snapshot-text {
  font-size: var(--font-size-base);
  line-height: 1.8;
  white-space: pre-wrap;
  color: var(--text);
  margin-bottom: 12px;
}

.notes-list {
  margin-bottom: 20px;
}

.note-item {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
}

.note-text {
  font-size: var(--font-size-base);
  line-height: 1.8;
  white-space: pre-wrap;
  margin-bottom: 8px;
}

.note-time {
  font-size: 14px;
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .detail-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-right {
    flex-direction: column;
  }
}
</style>
