<template>
  <div class="page-container">
    <h1 class="page-title">历史记录</h1>

    <!-- 查询表单 -->
    <div class="card">
      <div class="form-grid">
        <div class="form-group">
          <label class="form-label">开始日期</label>
          <input type="date" class="form-input" v-model="query.date_from" />
        </div>
        <div class="form-group">
          <label class="form-label">结束日期</label>
          <input type="date" class="form-input" v-model="query.date_to" />
        </div>
        <div class="form-group">
          <label class="form-label">组合名称</label>
          <input type="text" class="form-input" v-model="query.combination_name" placeholder="输入组合名称" />
        </div>
        <div class="form-group">
          <label class="form-label">股票名称</label>
          <input type="text" class="form-input" v-model="query.stock_name" placeholder="输入股票名称" />
        </div>
        <div class="form-group">
          <label class="form-label">模块</label>
          <select class="form-select" v-model="query.module_id">
            <option value="">全部模块</option>
            <option v-for="m in MODULES" :key="m.id" :value="m.id">{{ m.id }} - {{ m.name }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">关键词</label>
          <input type="text" class="form-input" v-model="query.keyword" placeholder="输入关键词" />
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" @click="onSearch">查询</button>
        <button class="btn btn-secondary" @click="onReset">重置</button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在查询，请稍候...</div>
    </div>

    <template v-else>
      <!-- 空状态 -->
      <div v-if="!items.length" class="empty-state">暂无历史记录</div>

      <!-- 结果列表 -->
      <template v-else>
        <div
          v-for="item in items"
          :key="item.id"
          class="card history-item"
          @click="goDetail(item.id)"
        >
          <div class="history-item-header">
            <span class="history-time">{{ formatTime(item.created_at) }}</span>
            <span :class="['status-tag', statusClass(item.status)]">{{ statusText(item.status) }}</span>
          </div>
          <div class="history-modules">
            <span class="history-label">使用模块：</span>
            <span v-if="item.modules && item.modules.length">
              {{ item.modules.map(m => m.module_name).join('、') }}
            </span>
            <span v-else class="text-secondary">无</span>
          </div>
          <div class="history-request">
            <span class="history-label">分析要求：</span>
            <span>{{ item.analysis_request || '无' }}</span>
          </div>
        </div>

        <!-- 分页 -->
        <div class="pagination">
          <button class="btn btn-secondary" :disabled="query.page <= 1" @click="changePage(query.page - 1)">上一页</button>
          <span class="page-info">第 {{ query.page }} 页 / 共 {{ totalPages }} 页（共 {{ total }} 条）</span>
          <button class="btn btn-secondary" :disabled="query.page >= totalPages" @click="changePage(query.page + 1)">下一页</button>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'
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
  const p = { page: query.page, page_size: PAGE_SIZE }
  if (query.date_from) p.date_from = query.date_from
  if (query.date_to) p.date_to = query.date_to
  if (query.combination_name) p.combination_name = query.combination_name
  if (query.stock_name) p.stock_name = query.stock_name
  if (query.module_id !== '') p.module_id = query.module_id
  if (query.keyword) p.keyword = query.keyword
  return p
}

async function fetchData() {
  loading.value = true
  try {
    const { data } = await historyApi.list(buildParams())
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    showToast('查询失败：' + (e.response?.data?.message || e.message), 'error')
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

function changePage(p) {
  if (p < 1 || p > totalPages.value) return
  query.page = p
  fetchData()
}

function goDetail(id) {
  router.push(`/history/${id}`)
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
  fetchData()
})
</script>

<style scoped>
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
  margin-bottom: 12px;
}

.history-time {
  font-size: var(--font-size-lg);
  font-weight: 700;
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
  .form-grid {
    grid-template-columns: 1fr;
  }

  .pagination {
    flex-direction: column;
    gap: 16px;
  }
}
</style>
