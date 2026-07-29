<template>
  <div class="page-container">
    <div class="analysis-heading">
      <div>
        <h1 class="page-title">组合分析</h1>
        <div class="analysis-date">本次分析使用：{{ formattedRecordDate }}</div>
      </div>
      <button class="btn btn-secondary" @click="backToWorkspace">返回该日工作台</button>
    </div>

    <section class="card date-warning">
      <strong>日期说明：</strong>
      本次只读取 {{ recordDate }} 的模块内容、股票名称和图片，并将该日期写入分析快照。其他日期的数据不会混入。
    </section>

    <section class="card">
      <h2 class="section-title">第一步：选择模块</h2>
      <p class="section-hint">点击下方模块卡片加入组合，再次点击取消选择；顺序可在下一步调整。</p>
      <div v-if="loadingCards" class="loading">
        <div class="loading-spinner"></div>
        <div>正在加载 {{ formattedRecordDate }} 的模块...</div>
      </div>
      <div v-else class="module-grid">
        <div
          v-for="card in cards"
          :key="card.module_id"
          class="module-card"
          :class="{ 'has-content': card.has_content, selected: isSelected(card.module_id) }"
          @click="toggleModule(card.module_id)"
        >
          <div class="module-card-number">{{ card.module_id + 1 }}</div>
          <div class="module-card-name">{{ card.module_name }}</div>
          <div v-if="card.display_title" class="module-card-title">{{ card.display_title }}</div>
          <div class="module-card-desc">{{ card.module_desc }}</div>
          <div class="module-card-info">
            <span :class="['module-card-status', card.has_content ? 'status-entered' : 'status-empty']">
              {{ card.has_content ? '已录入' : '未录入' }}
            </span>
            <span v-if="card.image_count > 0" class="module-card-images">图片 {{ card.image_count }} 张</span>
          </div>
          <div v-if="isSelected(card.module_id)" class="selected-mark">✓ 已选</div>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="section-toolbar">
        <div>
          <h2 class="section-title">第二步：调整组合顺序</h2>
          <p class="section-hint">AI 将严格按照此顺序读取模块。</p>
        </div>
        <button v-if="selectedModules.length" class="btn btn-danger btn-sm" @click="clearAll">清空全部</button>
      </div>
      <div v-if="selectedModules.length === 0" class="empty-state">
        还未选择任何模块，请从上方点击模块卡片加入组合。
      </div>
      <div v-else class="combination-list">
        <div v-for="(moduleId, index) in selectedModules" :key="moduleId" class="combination-item">
          <div class="combination-order">{{ index + 1 }}</div>
          <div class="combination-info">
            <div class="combination-name">{{ getModuleName(moduleId) }}</div>
            <div v-if="getModuleTitle(moduleId)" class="combination-title">{{ getModuleTitle(moduleId) }}</div>
          </div>
          <div class="combination-actions">
            <button class="btn btn-secondary btn-sm" :disabled="index === 0" @click="moveUp(index)">上移</button>
            <button
              class="btn btn-secondary btn-sm"
              :disabled="index === selectedModules.length - 1"
              @click="moveDown(index)"
            >
              下移
            </button>
            <button class="btn btn-danger btn-sm" @click="removeModule(moduleId)">删除</button>
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="section-toolbar">
        <div>
          <h2 class="section-title">常用组合</h2>
          <p class="section-hint">常用组合只保存模块编号和顺序，不保存某一天的内容。</p>
        </div>
        <button class="btn btn-secondary" :disabled="!selectedModules.length" @click="openSaveModal">
          保存为常用组合
        </button>
      </div>
      <div v-if="combinations.length === 0" class="empty-state">暂无常用组合。</div>
      <div v-else class="combination-list">
        <div v-for="combination in combinations" :key="combination.id" class="combination-item">
          <div class="combination-info">
            <div class="combination-name">{{ combination.name }}</div>
            <div class="combination-modules">
              {{ combination.module_ids.map(getModuleName).join(' → ') }}
            </div>
          </div>
          <div class="combination-actions">
            <button class="btn btn-primary btn-sm" @click="useCombination(combination)">使用</button>
            <button class="btn btn-danger btn-sm" @click="deleteCombination(combination.id)">删除</button>
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <h2 class="section-title">第三步：填写分析要求（可选）</h2>
      <div class="form-group">
        <label class="form-label">本次分析重点</label>
        <textarea
          v-model="analysisRequest"
          class="form-textarea"
          placeholder="例如：重点分析本周大盘走势和个股机会，关注风险点..."
        ></textarea>
      </div>
    </section>

    <section class="card text-center">
      <button
        class="btn btn-primary btn-lg w-full"
        :disabled="selectedModules.length === 0 || analyzing"
        @click="startAnalysis"
      >
        {{ analyzing ? '正在提交...' : `开始分析 ${recordDate}` }}
      </button>
      <p v-if="selectedModules.length === 0 && !analyzing" class="text-secondary mt-2">
        请先选择至少一个模块。
      </p>
    </section>

    <div v-if="showSaveModal" class="modal-overlay" @click.self="showSaveModal = false">
      <div class="modal">
        <div class="modal-title">保存为常用组合</div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">组合名称</label>
            <input
              v-model="newCombinationName"
              class="form-input"
              placeholder="请输入组合名称"
              @keyup.enter="saveCombination"
            />
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showSaveModal = false">取消</button>
          <button class="btn btn-primary" @click="saveCombination">保存</button>
        </div>
      </div>
    </div>

    <div v-if="confirmModal.show" class="modal-overlay" @click.self="confirmModal.show = false">
      <div class="modal">
        <div class="modal-title">{{ confirmModal.title }}</div>
        <div class="modal-body">{{ confirmModal.message }}</div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="confirmModal.show = false">取消</button>
          <button class="btn btn-danger" @click="confirmModal.onConfirm">确认</button>
        </div>
      </div>
    </div>

    <div v-if="analyzing" class="modal-overlay analyzing-overlay">
      <div class="analyzing-box">
        <div class="loading-spinner"></div>
        <div class="analyzing-text">正在提交 {{ recordDate }} 的分析任务...</div>
        <div class="analyzing-sub">提交成功后会自动进入结果页面，AI 在后台完成分析。</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { analysisApi, combinationsApi, modulesApi } from '../api'
import {
  currentRecordDate,
  formatRecordDate,
  isValidRecordDate,
  setCurrentRecordDate,
} from '../dateContext'

const router = useRouter()
const route = useRoute()
const showToast = inject('toast')
const recordDate = currentRecordDate
const formattedRecordDate = computed(() => formatRecordDate(recordDate.value))

const MODULE_NAMES = [
  '一周策略', '股票1', '股票2', '股票3', '股票4', '技术派观点',
  '钱说观点', '大盘走势', '反向操作', 'AI复盘', '行业板块', '操作建议',
]

const cards = ref([])
const loadingCards = ref(true)
const selectedModules = ref([])
const combinations = ref([])
const analysisRequest = ref('')
const analyzing = ref(false)
const showSaveModal = ref(false)
const newCombinationName = ref('')
const confirmModal = ref({ show: false, title: '', message: '', onConfirm: null })

function getCard(id) {
  return cards.value.find((card) => card.module_id === id)
}

function getModuleName(id) {
  return getCard(id)?.module_name || MODULE_NAMES[id] || `模块${id + 1}`
}

function getModuleTitle(id) {
  return getCard(id)?.display_title || ''
}

async function loadCards() {
  loadingCards.value = true
  try {
    const response = await modulesApi.getCards(recordDate.value)
    cards.value = response.data
  } catch (error) {
    showToast(error.response?.data?.detail || '加载模块失败', 'error')
  } finally {
    loadingCards.value = false
  }
}

async function loadCombinations() {
  try {
    const response = await combinationsApi.list()
    combinations.value = response.data
  } catch {
    showToast('加载常用组合失败', 'error')
  }
}

function toggleModule(id) {
  const index = selectedModules.value.indexOf(id)
  if (index >= 0) selectedModules.value.splice(index, 1)
  else selectedModules.value.push(id)
}

function isSelected(id) {
  return selectedModules.value.includes(id)
}

function moveUp(index) {
  if (index <= 0) return
  const values = [...selectedModules.value]
  ;[values[index - 1], values[index]] = [values[index], values[index - 1]]
  selectedModules.value = values
}

function moveDown(index) {
  if (index >= selectedModules.value.length - 1) return
  const values = [...selectedModules.value]
  ;[values[index], values[index + 1]] = [values[index + 1], values[index]]
  selectedModules.value = values
}

function removeModule(id) {
  confirmModal.value = {
    show: true,
    title: '移除模块',
    message: `确定要从组合中移除“${getModuleName(id)}”吗？`,
    onConfirm: () => {
      selectedModules.value = selectedModules.value.filter((moduleId) => moduleId !== id)
      confirmModal.value.show = false
      showToast('已移除', 'success')
    },
  }
}

function clearAll() {
  confirmModal.value = {
    show: true,
    title: '清空全部',
    message: '确定要清空所有已选模块吗？',
    onConfirm: () => {
      selectedModules.value = []
      confirmModal.value.show = false
      showToast('已清空', 'success')
    },
  }
}

function useCombination(combination) {
  selectedModules.value = [...combination.module_ids]
  showToast(`已载入组合“${combination.name}”`, 'success')
}

function openSaveModal() {
  if (!selectedModules.value.length) {
    showToast('请先选择模块', 'warning')
    return
  }
  newCombinationName.value = ''
  showSaveModal.value = true
}

async function saveCombination() {
  const name = newCombinationName.value.trim()
  if (!name) {
    showToast('请输入组合名称', 'warning')
    return
  }
  try {
    await combinationsApi.create(name, selectedModules.value)
    showToast('保存成功', 'success')
    showSaveModal.value = false
    await loadCombinations()
  } catch (error) {
    showToast(error.response?.data?.detail || '保存失败', 'error')
  }
}

function deleteCombination(combinationId) {
  confirmModal.value = {
    show: true,
    title: '删除组合',
    message: '确定要删除这个常用组合吗？',
    onConfirm: async () => {
      try {
        await combinationsApi.delete(combinationId)
        showToast('已删除', 'success')
        await loadCombinations()
      } catch (error) {
        showToast(error.response?.data?.detail || '删除失败', 'error')
      }
      confirmModal.value.show = false
    },
  }
}

async function startAnalysis() {
  if (!selectedModules.value.length) {
    showToast('请先选择模块', 'warning')
    return
  }
  if (analyzing.value) return
  analyzing.value = true
  try {
    const response = await analysisApi.create(
      selectedModules.value,
      analysisRequest.value,
      '',
      recordDate.value,
    )
    showToast(`已提交 ${recordDate.value} 的分析任务`, 'success')
    router.push({ path: `/result/${response.data.id}`, query: { date: recordDate.value } })
  } catch (error) {
    analyzing.value = false
    showToast('分析启动失败：' + (error.response?.data?.detail || error.message || '请求失败'), 'error')
  }
}

function backToWorkspace() {
  router.push({ path: '/', query: { date: recordDate.value } })
}

onMounted(() => {
  const queryDate = String(route.query.date || '')
  if (isValidRecordDate(queryDate)) setCurrentRecordDate(queryDate)
  const combination = String(route.query.combination || '')
  if (combination) {
    selectedModules.value = combination
      .split(',')
      .map((value) => Number.parseInt(value.trim(), 10))
      .filter((value) => Number.isInteger(value) && value >= 0 && value <= 11)
  }
  if (route.query.request) analysisRequest.value = String(route.query.request)
  loadCards()
  loadCombinations()
})
</script>

<style scoped>
.analysis-heading,
.section-toolbar,
.combination-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.analysis-date {
  color: var(--primary);
  font-size: 18px;
  font-weight: 700;
  margin-top: -12px;
  margin-bottom: 20px;
}
.date-warning {
  background: #eef4ff;
  border-left: 5px solid var(--primary);
  line-height: 1.8;
}
.section-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--text);
}
.section-hint {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin-bottom: 20px;
}
.module-card.selected {
  border-color: var(--primary);
  background: #e8f0fe;
  box-shadow: 0 4px 12px rgba(26, 115, 232, 0.25);
}
.module-card-title,
.combination-title {
  color: var(--primary);
  font-weight: 700;
}
.module-card-images,
.combination-modules {
  font-size: 16px;
  color: var(--text-secondary);
}
.selected-mark {
  position: absolute;
  bottom: 12px;
  right: 16px;
  background: var(--primary);
  color: #fff;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 16px;
  font-weight: 600;
}
.combination-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.combination-actions {
  justify-content: flex-end;
}
.analyzing-overlay { background: rgba(0, 0, 0, 0.7); }
.analyzing-box {
  background: #fff;
  border-radius: var(--radius);
  padding: 48px 40px;
  text-align: center;
  max-width: 520px;
  width: 90%;
}
.analyzing-box .loading-spinner { margin: 0 auto 24px; }
.analyzing-text { font-size: var(--font-size-xl); font-weight: 600; margin-bottom: 12px; }
.analyzing-sub { font-size: var(--font-size-base); color: var(--text-secondary); }
@media (max-width: 720px) {
  .combination-item { align-items: flex-start; }
  .combination-actions { width: 100%; }
}
</style>
