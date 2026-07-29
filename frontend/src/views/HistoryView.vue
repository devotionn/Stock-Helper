<template>
  <div class="page-container">
    <h1 class="page-title">历史记录</h1>
    <p class="history-page-hint">日期筛选按照“投研日期”查询；实际分析时间单独显示。</p>

    <div class="card">
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">投研开始日期</label>
          <input v-model="query.date_from" type="date" class="form-input" />
        </div>
        <div class="form-group">
          <label class="form-label">投研结束日期</label>
          <input v-model="query.date_to" type="date" class="form-input" />
        </div>
        <div class="form-group">
          <label class="form-label">组合名称</label>
          <input v-model="query.combination_name" type="text" class="form-input" placeholder="输入组合名称" />
        </div>
        <div class="form-group">
          <label class="form-label">股票名称</label>
          <input v-model="query.stock_name" type="text" class="form-input" placeholder="例如：宁德时代" />
        </div>
        <div class="form-group">
          <label class="form-label">模块</label>
          <select v-model="query.module_id" class="form-select">
            <option value="">全部模块</option>
            <option v-for="module in MODULES" :key="module.id" :value="module.id">
              {{ module.id + 1 }} - {{ module.name }}
            </option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">关键词</label>
          <input v-model="query.keyword" type="text" class="form-input" placeholder="搜索文字、标的或结果" />
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" @click="onSearch">查询</button>
        <button class="btn btn-secondary" @click="onReset">重置</button>
      </div>
    </div>

    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在查询，请稍候...</div>
    </div>

    <template v-else>
      <div v-if="!items.length" class="empty-state">暂无历史记录</div>
      <template v-else>
        <div
          v-for="item in items"
          :key="item.id"
          class="card history-item"
          @click="goDetail(item.id)"
        >
          <div class="history-item-header">
            <div>
              <div class="history-record-date">投研日期：{{ item.record_date || '未记录' }}</div>
              <div class="history-time">实际分析：{{ formatTime(item.created_at) }}</div>
            </div>
            <span :class="['status-tag', statusClass(item.status)]">{{ statusText(item.status) }}</span>
          </div>
          <div class="history-modules">
            <span class="history-label">使用模块：</span>
            <span v-if="item.modules?.length">
              {{ item.modules.map(moduleDisplayName).join('、') }}
            </span>
            <span v-else class="text-secondary">无</span>
          </div>
          <div class="history-request">
            <span class="history-label">分析要求：</span>
            <span>{{ item.analysis_request || '无' }}</span>
          </div>
        </div>

        <div class="pagination">
          <button class="btn btn-secondary" :disabled="query.page <= 1" @click="changePage(query.page - 1)">
            上一页
          </button>
          <span class="page-info">第 {{ query.page }} 页 / 共 {{ totalPages }} 页（共 {{ total }} 条）</span>
          <button class="btn btn-secondary" :disabled="query.page >= totalPages" @click="changePage(query.page + 1)">
            下一页
          </button>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { historyApi } from '../api'

const router = useRouter()
const showToast = inject('toast')

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

const PAGE_SIZE = 10
const loading = ref(false)
const items = ref([])
const total = ref(0)
const query = reactive({
  date_from: '',
  date_to: '',
  combination_name: '',
  stock_name: '',
  module_id: '',
  keyword: '',
  page: 1,
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function buildParams() {
  const params = { page: query.page, page_size: PAGE_SIZE }
  if (query.date_from) params.date_from = query.date_from
  if (query.date_to) params.date_to = query.date_to
  if (query.combination_name) params.combination_name = query.combination_name
  if (query.stock_name) params.stock_name = query.stock_name
  if (query.module_id !== '') params.module_id = query.module_id
  if (query.keyword) params.keyword = query.keyword
  return params
}

async function fetchData() {
  loading.value = true
  try {
    const { data } = await historyApi.list(buildParams())
    items.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    showToast('查询失败：' + (error.response?.data?.detail || error.message), 'error')
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onSearch() {
  query.page = 1
  fetchData()
}

function onReset() {
  query.date_from = ''
  query.date_to = ''
  query.combination_name = ''
  query.stock_name = ''
  query.module_id = ''
  query.keyword = ''
  query.page = 1
  fetchData()
}

function changePage(page) {
  if (page < 1 || page > totalPages.value) return
  query.page = page
  fetchData()
}

function goDetail(id) {
  router.push(`/history/${id}`)
}

function moduleDisplayName(module) {
  return module.display_title
    ? `${module.module_name}（${module.display_title}）`
    : module.module_name
}

function formatTime(value) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  const pad = (number) => String(number).padStart(2, '0')
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
}

function statusText(status) {
  const map = {
    completed: '已完成',
    completed_with_warning: '已完成（格式提醒）',
    failed: '失败',
    running: '进行中',
    pending: '等待中',
    interrupted: '已中断',
  }
  return map[status] || status || '未知'
}

function statusClass(status) {
  const map = {
    completed: 'status-completed',
    completed_with_warning: 'status-warning',
    failed: 'status-failed',
    running: 'status-running',
    pending: 'status-pending',
    interrupted: 'status-failed',
  }
  return map[status] || 'status-pending'
}

onMounted(fetchData)
</script>

<style scoped>
.history-page-hint {
  color: var(--text-secondary);
  margin-top: -12px;
  margin-bottom: 22px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px 24px;
}
.form-actions {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}
.history-item {
  cursor: pointer;
  transition: all 0.2s;
}
.history-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  border-left: 4px solid var(--primary);
}
.history-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}
.history-record-date {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--primary);
}
.history-time {
  color: var(--text-secondary);
  margin-top: 4px;
}
.status-tag {
  display: inline-block;
  padding: 4px 16px;
  border-radius: 20px;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}
.status-completed { background: #e6f4ea; color: var(--success); }
.status-warning { background: #fff3cd; color: #7a5200; }
.status-failed { background: #fce8e6; color: var(--danger); }
.status-running { background: #e8f0fe; color: var(--primary); }
.status-pending { background: #f1f3f4; color: var(--text-secondary); }
.history-modules,
.history-request {
  font-size: var(--font-size-base);
  line-height: 1.8;
  margin-top: 4px;
}
.history-label {
  font-weight: 600;
  color: var(--text-secondary);
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  margin-top: 24px;
}
.page-info {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
}
@media (max-width: 768px) {
  .form-grid { grid-template-columns: 1fr; }
  .pagination { flex-direction: column; gap: 16px; }
  .history-item-header { align-items: flex-start; }
}
</style>
