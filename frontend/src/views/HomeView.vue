<template>
  <div class="page-container">
    <section class="date-panel">
      <div class="date-panel-main">
        <div>
          <div class="date-label">当前投研日期</div>
          <h1 class="date-title">{{ formattedSelectedDate }}</h1>
          <div class="date-summary">
            <span>完成 {{ workspace.completed_count || 0 }}/{{ workspace.total_count || 12 }}</span>
            <span>AI 分析 {{ workspace.analysis_count || 0 }} 次</span>
            <span :class="['workspace-status', workspace.status || 'empty']">
              {{ workspaceStatusText }}
            </span>
          </div>
        </div>
        <div class="date-actions">
          <button class="btn btn-secondary" @click="changeDay(-1)">← 上一天</button>
          <button class="btn btn-primary" @click="goToday">今天</button>
          <button class="btn btn-secondary" @click="changeDay(1)">下一天 →</button>
          <button class="btn btn-secondary" @click="calendarOpen = !calendarOpen">
            {{ calendarOpen ? '收起月历' : '展开月历' }}
          </button>
        </div>
      </div>

      <div v-if="calendarOpen" class="calendar-card">
        <div class="calendar-header">
          <button class="btn btn-secondary btn-sm" @click="changeMonth(-1)">← 上个月</button>
          <h2>{{ calendarTitle }}</h2>
          <button class="btn btn-secondary btn-sm" @click="changeMonth(1)">下个月 →</button>
        </div>
        <div class="calendar-weekdays" aria-hidden="true">
          <span v-for="weekday in weekdays" :key="weekday">{{ weekday }}</span>
        </div>
        <div class="calendar-grid">
          <button
            v-for="cell in monthCells"
            :key="cell.date"
            type="button"
            :class="[
              'calendar-day',
              { outside: !cell.currentMonth, selected: cell.date === selectedDate, today: cell.date === today },
              calendarStatus(cell.date),
            ]"
            :aria-label="calendarAriaLabel(cell.date)"
            @click="selectDate(cell.date)"
          >
            <span class="calendar-day-number">{{ cell.day }}</span>
            <span class="calendar-day-progress">{{ calendarProgress(cell.date) }}</span>
            <span v-if="calendarInfo(cell.date)?.analysis_count" class="calendar-analysis">已分析</span>
          </button>
        </div>
        <div class="calendar-legend">
          <span><i class="legend-dot partial"></i>部分录入</span>
          <span><i class="legend-dot complete"></i>12 项完成</span>
          <span><i class="legend-dot analyzed"></i>已进行 AI 分析</span>
        </div>
      </div>

      <div class="workspace-actions">
        <button class="btn btn-secondary" :disabled="copying" @click="copyPreviousDay">
          {{ copying ? '正在复制...' : '复制上一日基础内容' }}
        </button>
        <button class="btn btn-primary" @click="goAnalysis">开始组合分析</button>
      </div>
      <p class="copy-hint">复制默认包含策略、股票、观点、大盘与行业板块，不复制 AI 复盘和操作建议；已有内容不会被覆盖。</p>
    </section>

    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在加载 {{ formattedSelectedDate }} 的模块...</div>
    </div>

    <div v-else-if="error" class="empty-state">
      加载失败：{{ error }}
      <div class="mt-4">
        <button class="btn btn-primary" @click="loadWorkspace">重新加载</button>
      </div>
    </div>

    <div v-else class="module-grid">
      <div
        v-for="card in cards"
        :key="card.module_id"
        :class="['module-card', { 'has-content': card.has_content }]"
        @click="goToModule(card.module_id)"
      >
        <div class="module-card-number">{{ card.module_id + 1 }}</div>
        <div class="module-card-name">{{ card.module_name }}</div>
        <div v-if="card.display_title" class="module-card-title">{{ card.display_title }}</div>
        <div class="module-card-desc">{{ card.module_desc }}</div>
        <div class="module-card-info">
          <span v-if="card.text_summary">{{ card.text_summary }}</span>
          <span v-else class="text-secondary">暂无文字内容</span>
          <span>图片：{{ card.image_count }} 张</span>
          <span v-if="card.updated_at">最后更新：{{ card.updated_at }}</span>
        </div>
        <span :class="['module-card-status', card.has_content ? 'status-entered' : 'status-empty']">
          {{ card.has_content ? '已录入' : '未录入' }}
        </span>
        <button class="btn btn-primary btn-sm module-edit-button" @click.stop="goToModule(card.module_id)">
          查看 / 编辑
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { workspacesApi } from '../api'
import {
  currentRecordDate,
  formatRecordDate,
  isValidRecordDate,
  setCurrentRecordDate,
  shiftRecordDate,
} from '../dateContext'

const router = useRouter()
const route = useRoute()
const showToast = inject('toast')

const weekdays = ['日', '一', '二', '三', '四', '五', '六']
const today = shiftRecordDate('', 0)
const selectedDate = currentRecordDate
const calendarOpen = ref(false)
const displayedMonth = ref(selectedDate.value.slice(0, 7))
const calendarDays = ref({})
const workspace = ref({ completed_count: 0, total_count: 12, analysis_count: 0, status: 'empty' })
const cards = ref([])
const loading = ref(true)
const copying = ref(false)
const error = ref('')

const formattedSelectedDate = computed(() => formatRecordDate(selectedDate.value))
const calendarTitle = computed(() => {
  const [year, month] = displayedMonth.value.split('-').map(Number)
  return `${year}年${month}月`
})
const workspaceStatusText = computed(() => {
  const map = {
    empty: '尚未录入',
    partial: '部分完成',
    complete: '全部完成',
    analyzed: '已进行分析',
  }
  return map[workspace.value.status] || '尚未录入'
})

function dateParts(value) {
  const [year, month, day] = value.split('-').map(Number)
  return { year, month, day }
}

function formatDateObject(value) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const monthCells = computed(() => {
  const [year, month] = displayedMonth.value.split('-').map(Number)
  const first = new Date(year, month - 1, 1)
  const start = new Date(year, month - 1, 1 - first.getDay())
  return Array.from({ length: 42 }, (_, index) => {
    const current = new Date(start)
    current.setDate(start.getDate() + index)
    return {
      date: formatDateObject(current),
      day: current.getDate(),
      currentMonth: current.getMonth() === month - 1,
    }
  })
})

function calendarInfo(value) {
  return calendarDays.value[value] || null
}

function calendarProgress(value) {
  const info = calendarInfo(value)
  return info ? `${info.completed_count}/12` : '0/12'
}

function calendarStatus(value) {
  return calendarInfo(value)?.status || 'empty'
}

function calendarAriaLabel(value) {
  const info = calendarInfo(value)
  const progress = info ? `${info.completed_count} 项已完成` : '没有录入内容'
  const analyzed = info?.analysis_count ? `，已分析 ${info.analysis_count} 次` : ''
  return `${formatRecordDate(value)}，${progress}${analyzed}`
}

async function loadWorkspace() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await workspacesApi.get(selectedDate.value)
    workspace.value = data
    cards.value = data.cards || []
    await loadCalendar()
  } catch (requestError) {
    error.value = requestError.response?.data?.detail || requestError.message || '未知错误'
    showToast('加载投研日期数据失败', 'error')
  } finally {
    loading.value = false
  }
}

async function loadCalendar() {
  try {
    const { data } = await workspacesApi.calendar(displayedMonth.value)
    calendarDays.value = Object.fromEntries((data.days || []).map((item) => [item.date, item]))
  } catch {
    showToast('月历状态加载失败', 'warning')
  }
}

async function selectDate(value) {
  if (!isValidRecordDate(value)) return
  setCurrentRecordDate(value)
  displayedMonth.value = value.slice(0, 7)
  await router.replace({ path: '/', query: { date: value } })
  await loadWorkspace()
}

function changeDay(offset) {
  selectDate(shiftRecordDate(selectedDate.value, offset))
}

function goToday() {
  selectDate(today)
}

function changeMonth(offset) {
  const [year, month] = displayedMonth.value.split('-').map(Number)
  const target = new Date(year, month - 1 + offset, 1)
  displayedMonth.value = `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, '0')}`
  loadCalendar()
}

async function copyPreviousDay() {
  const sourceDate = shiftRecordDate(selectedDate.value, -1)
  const confirmed = window.confirm(
    `将 ${sourceDate} 的基础模块复制到 ${selectedDate.value}。\n已有内容不会被覆盖，是否继续？`,
  )
  if (!confirmed) return
  copying.value = true
  try {
    const { data } = await workspacesApi.copy(
      selectedDate.value,
      sourceDate,
      [0, 1, 2, 3, 4, 5, 6, 7, 8, 10],
      false,
    )
    showToast(data.message, data.skipped_module_ids?.length ? 'warning' : 'success')
    await loadWorkspace()
  } catch (requestError) {
    showToast(requestError.response?.data?.detail || '复制失败', 'error')
  } finally {
    copying.value = false
  }
}

function goToModule(id) {
  router.push({ path: `/module/${id}`, query: { date: selectedDate.value } })
}

function goAnalysis() {
  router.push({ path: '/analysis', query: { date: selectedDate.value } })
}

watch(displayedMonth, loadCalendar)

onMounted(() => {
  const queryDate = String(route.query.date || '')
  if (isValidRecordDate(queryDate)) setCurrentRecordDate(queryDate)
  displayedMonth.value = selectedDate.value.slice(0, 7)
  loadWorkspace()
})
</script>

<style scoped>
.date-panel {
  background: #fff;
  border: 2px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 28px;
}
.date-panel-main {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: center;
  flex-wrap: wrap;
}
.date-label {
  color: var(--text-secondary);
  font-size: var(--font-size-base);
  margin-bottom: 4px;
}
.date-title {
  margin: 0;
  font-size: 30px;
}
.date-summary,
.date-actions,
.workspace-actions,
.calendar-legend {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.date-summary {
  margin-top: 12px;
  font-size: 17px;
}
.workspace-status {
  padding: 4px 12px;
  border-radius: 999px;
  font-weight: 700;
  background: #eef1f5;
}
.workspace-status.partial { background: #fff3cd; color: #7a5200; }
.workspace-status.complete { background: #d9f2e2; color: #146c43; }
.workspace-status.analyzed { background: #dce9ff; color: #174ea6; }
.workspace-actions {
  margin-top: 20px;
}
.copy-hint {
  color: var(--text-secondary);
  margin: 10px 0 0;
}
.calendar-card {
  margin-top: 24px;
  border-top: 2px solid var(--border);
  padding-top: 20px;
}
.calendar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.calendar-header h2 { margin: 0; }
.calendar-weekdays,
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
}
.calendar-weekdays span {
  text-align: center;
  font-weight: 700;
  padding: 8px;
}
.calendar-day {
  min-height: 94px;
  border: 1px solid var(--border);
  background: #fff;
  padding: 8px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  cursor: pointer;
  font: inherit;
  color: var(--text);
}
.calendar-day:hover { background: #f4f8ff; }
.calendar-day.outside { opacity: 0.45; }
.calendar-day.selected { outline: 3px solid var(--primary); outline-offset: -3px; }
.calendar-day.today .calendar-day-number { background: var(--primary); color: #fff; }
.calendar-day.partial { background: #fffaf0; }
.calendar-day.complete { background: #effaf3; }
.calendar-day.analyzed { background: #eef4ff; }
.calendar-day-number {
  min-width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-weight: 700;
}
.calendar-day-progress { font-size: 15px; }
.calendar-analysis { color: #174ea6; font-size: 14px; font-weight: 700; }
.calendar-legend { margin-top: 14px; color: var(--text-secondary); }
.legend-dot { width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 5px; }
.legend-dot.partial { background: #f5b942; }
.legend-dot.complete { background: #42a66b; }
.legend-dot.analyzed { background: #4d7fd6; }
.module-card-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--primary);
  margin-bottom: 6px;
}
.module-edit-button { width: 100%; }
@media (max-width: 720px) {
  .calendar-day { min-height: 72px; padding: 5px; }
  .calendar-day-progress, .calendar-analysis { font-size: 12px; }
  .date-title { font-size: 24px; }
}
</style>
