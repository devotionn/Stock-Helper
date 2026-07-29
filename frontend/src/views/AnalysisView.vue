<template>
  <div class="page-container">
    <h1 class="page-title">组合分析</h1>

    <!-- 第一步：选择模块 -->
    <section class="card">
      <h2 class="section-title">第一步：选择模块</h2>
      <p class="section-hint">点击下方模块卡片加入组合，再次点击取消选择</p>
      <div v-if="loadingCards" class="loading">
        <div class="loading-spinner"></div>
        <div>正在加载模块...</div>
      </div>
      <div v-else class="module-grid">
        <div
          v-for="card in cards"
          :key="card.module_id"
          class="module-card"
          :class="{ 'has-content': card.has_content, 'selected': isSelected(card.module_id) }"
          @click="toggleModule(card.module_id)"
        >
          <div class="module-card-number">{{ card.module_id }}</div>
          <div class="module-card-name">{{ card.module_name }}</div>
          <div class="module-card-desc">{{ card.module_desc }}</div>
          <div class="module-card-info">
            <span class="module-card-status" :class="card.has_content ? 'status-entered' : 'status-empty'">
              {{ card.has_content ? '已录入' : '未录入' }}
            </span>
            <span v-if="card.image_count > 0" class="module-card-images">📷 {{ card.image_count }}张图</span>
          </div>
          <div v-if="isSelected(card.module_id)" class="selected-mark">✓ 已选</div>
        </div>
      </div>
    </section>

    <!-- 第二步：调整组合顺序 -->
    <section class="card">
      <div class="flex items-center justify-between mb-4">
        <h2 class="section-title">第二步：调整组合顺序</h2>
        <button v-if="selectedModules.length > 0" class="btn btn-danger btn-sm" @click="clearAll">
          清空全部
        </button>
      </div>
      <div v-if="selectedModules.length === 0" class="empty-state">
        还未选择任何模块，请从上方点击模块卡片加入组合
      </div>
      <div v-else class="combination-list">
        <div v-for="(modId, index) in selectedModules" :key="modId" class="combination-item">
          <div class="combination-order">{{ index + 1 }}</div>
          <div class="combination-name">{{ getModuleName(modId) }}</div>
          <div class="flex gap-2">
            <button class="btn btn-secondary btn-sm" :disabled="index === 0" @click="moveUp(index)">
              上移
            </button>
            <button
              class="btn btn-secondary btn-sm"
              :disabled="index === selectedModules.length - 1"
              @click="moveDown(index)"
            >
              下移
            </button>
            <button class="btn btn-danger btn-sm" @click="removeModule(modId)">
              删除
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- 常用组合 -->
    <section class="card">
      <div class="flex items-center justify-between mb-4">
        <h2 class="section-title">常用组合</h2>
        <button
          class="btn btn-secondary"
          :disabled="selectedModules.length === 0"
          @click="openSaveModal"
        >
          保存为常用组合
        </button>
      </div>
      <div v-if="combinations.length === 0" class="empty-state">
        暂无常用组合，选择模块后可保存
      </div>
      <div v-else class="combination-list">
        <div v-for="comb in combinations" :key="comb.id" class="combination-item">
          <div class="combination-info">
            <div class="combination-name">{{ comb.name }}</div>
            <div class="combination-modules">{{ comb.module_ids.map(getModuleName).join(' -> ') }}</div>
          </div>
          <div class="flex gap-2">
            <button class="btn btn-primary btn-sm" @click="useCombination(comb)">使用</button>
            <button class="btn btn-danger btn-sm" @click="deleteCombination(comb.id)">删除</button>
          </div>
        </div>
      </div>
    </section>

    <!-- 第三步：分析要求 -->
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

    <!-- 开始分析 -->
    <section class="card text-center">
      <button
        class="btn btn-primary btn-lg w-full"
        :disabled="selectedModules.length === 0 || analyzing"
        @click="startAnalysis"
      >
        {{ analyzing ? 'AI分析中...' : '开始分析' }}
      </button>
      <p v-if="selectedModules.length === 0 && !analyzing" class="text-secondary mt-2">
        请先选择至少一个模块
      </p>
    </section>

    <!-- 保存组合模态框 -->
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

    <!-- 确认模态框 -->
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

    <!-- 分析中加载遮罩 -->
    <div v-if="analyzing" class="modal-overlay analyzing-overlay">
      <div class="analyzing-box">
        <div class="loading-spinner"></div>
        <div class="analyzing-text">AI正在分析中，请耐心等待...</div>
        <div class="analyzing-sub">分析可能需要30-120秒，请勿关闭页面</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, inject, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { modulesApi, combinationsApi, analysisApi } from '../api'

const router = useRouter()
const route = useRoute()
const showToast = inject('toast')

const MODULE_NAMES = [
  '一周策略', '股票1', '股票2', '股票3', '股票4',
  '技术派观点', '钱说观点', '大盘走势', '反向操作',
  'AI复盘', '行业板块', '操作建议',
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

function getModuleName(id) {
  const card = cards.value.find((c) => c.module_id === id)
  if (card) return card.module_name
  return MODULE_NAMES[id] || `模块${id}`
}

async function loadCards() {
  loadingCards.value = true
  try {
    const res = await modulesApi.getCards()
    cards.value = res.data
  } catch (e) {
    showToast('加载模块失败', 'error')
  } finally {
    loadingCards.value = false
  }
}

async function loadCombinations() {
  try {
    const res = await combinationsApi.list()
    combinations.value = res.data
  } catch (e) {
    showToast('加载常用组合失败', 'error')
  }
}

function toggleModule(id) {
  const idx = selectedModules.value.indexOf(id)
  if (idx >= 0) {
    selectedModules.value.splice(idx, 1)
  } else {
    selectedModules.value.push(id)
  }
}

function isSelected(id) {
  return selectedModules.value.includes(id)
}

function moveUp(index) {
  if (index === 0) return
  const arr = selectedModules.value
  const tmp = arr[index - 1]
  arr[index - 1] = arr[index]
  arr[index] = tmp
}

function moveDown(index) {
  const arr = selectedModules.value
  if (index === arr.length - 1) return
  const tmp = arr[index + 1]
  arr[index + 1] = arr[index]
  arr[index] = tmp
}

function removeModule(id) {
  confirmModal.value = {
    show: true,
    title: '移除模块',
    message: `确定要从组合中移除"${getModuleName(id)}"吗？`,
    onConfirm: () => {
      const idx = selectedModules.value.indexOf(id)
      if (idx >= 0) selectedModules.value.splice(idx, 1)
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

function useCombination(comb) {
  selectedModules.value = [...comb.module_ids]
  showToast(`已载入组合"${comb.name}"`, 'success')
}

function openSaveModal() {
  if (selectedModules.value.length === 0) {
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
  } catch (e) {
    showToast('保存失败', 'error')
  }
}

function deleteCombination(combId) {
  confirmModal.value = {
    show: true,
    title: '删除组合',
    message: '确定要删除这个常用组合吗？',
    onConfirm: async () => {
      try {
        await combinationsApi.delete(combId)
        showToast('已删除', 'success')
        await loadCombinations()
      } catch (e) {
        showToast('删除失败', 'error')
      }
      confirmModal.value.show = false
    },
  }
}

async function startAnalysis() {
  if (selectedModules.value.length === 0) {
    showToast('请先选择模块', 'warning')
    return
  }
  analyzing.value = true
  try {
    const res = await analysisApi.create(selectedModules.value, analysisRequest.value, '')
    const data = res.data
    if (data.status === 'failed') {
      analyzing.value = false
      showToast('分析失败：' + (data.error_message || '未知错误'), 'error')
      return
    }
    showToast('分析完成', 'success')
    router.push(`/result/${data.id}`)
  } catch (e) {
    analyzing.value = false
    const msg = e.response?.data?.detail || e.message || '请求失败'
    showToast('分析启动失败：' + msg, 'error')
  }
}

onMounted(() => {
  loadCards()
  loadCombinations()
  // 支持从历史记录“重新分析”跳转，预填模块组合
  const comb = route.query.combination
  if (comb) {
    selectedModules.value = String(comb)
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n) && n >= 0 && n <= 11)
  }
  // 预填分析要求
  const req = route.query.request
  if (req) {
    analysisRequest.value = String(req)
  }
})
</script>

<style scoped>
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

.module-card-images {
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

.combination-modules {
  font-size: 16px;
  color: var(--text-secondary);
  word-break: break-all;
}

.analyzing-overlay {
  background: rgba(0, 0, 0, 0.7);
}

.analyzing-box {
  background: #fff;
  border-radius: var(--radius);
  padding: 48px 40px;
  text-align: center;
  max-width: 480px;
  width: 90%;
}

.analyzing-box .loading-spinner {
  margin: 0 auto 20px;
}

.analyzing-text {
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
}

.analyzing-sub {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
}
</style>
