<template>
  <div class="page-container">
    <h1 class="page-title">分析结果</h1>

    <!-- 加载中 -->
    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div>正在加载...</div>
    </div>

    <template v-else-if="analysis">
      <!-- 返回按钮 -->
      <button class="btn btn-secondary mb-4" @click="goBack">← 返回组合分析</button>

      <!-- 分析中 -->
      <div v-if="analysis.status === 'running'" class="loading analyzing-loading">
        <div class="loading-spinner"></div>
        <div class="analyzing-text">AI正在分析中，请耐心等待...</div>
        <div class="analyzing-sub">分析可能需要30-120秒，页面将自动刷新结果</div>
      </div>

      <!-- 失败 -->
      <div v-else-if="analysis.status === 'failed'" class="card">
        <div class="analysis-warning">❌ 分析失败</div>
        <div class="analysis-section-content">
          {{ analysis.error_message || '分析过程中出现错误，请稍后重试' }}
        </div>
        <button class="btn btn-secondary mt-4" @click="goBack">返回重新分析</button>
      </div>

      <!-- 完成 -->
      <template v-else-if="analysis.status === 'completed'">
        <!-- 免责声明 -->
        <div class="analysis-warning">⚠️ 本分析仅供参考，不构成投资建议</div>

        <!-- 分析信息 -->
        <section class="card">
          <h2 class="section-title">分析信息</h2>
          <div class="info-row">
            <span class="info-label">使用模块：</span>
            <div class="info-value">
              <template v-for="(modId, idx) in analysis.combination" :key="modId">
                <span class="combo-step">
                  <span class="combo-order">{{ idx + 1 }}</span>
                  <span class="combo-name">{{ getModuleName(modId) }}</span>
                </span>
                <span v-if="idx < analysis.combination.length - 1" class="combo-arrow">-></span>
              </template>
            </div>
          </div>
          <div class="info-row">
            <span class="info-label">分析要求：</span>
            <div class="info-value">{{ analysis.analysis_request || '（未填写）' }}</div>
          </div>
          <div class="info-row">
            <span class="info-label">开始时间：</span>
            <div class="info-value">{{ formatTime(analysis.started_at || analysis.created_at) }}</div>
          </div>
          <div class="info-row">
            <span class="info-label">完成时间：</span>
            <div class="info-value">{{ formatTime(analysis.completed_at) }}</div>
          </div>
        </section>

        <!-- 分析结果 -->
        <section class="card">
          <h2 class="section-title">分析结果</h2>
          <div v-if="useRaw" class="analysis-section">
            <div class="analysis-section-title">原始结果</div>
            <div class="analysis-section-content">{{ analysis.raw_result || '暂无结果' }}</div>
          </div>
          <template v-else>
            <div v-for="key in SECTION_KEYS" :key="key" class="analysis-section">
              <div class="analysis-section-title">{{ key }}</div>
              <div class="analysis-section-content">{{ parsedResult[key] || '暂无内容' }}</div>
            </div>
          </template>
        </section>

        <!-- 保存到模块 -->
        <section class="card">
          <h2 class="section-title">保存到模块</h2>
          <p class="section-hint">将本次分析结果保存到对应模块，方便后续查看</p>
          <div class="flex gap-4 save-buttons">
            <button
              class="btn btn-success"
              :disabled="saving !== null"
              @click="saveToModule(9, 'AI复盘')"
            >
              {{ saving === 9 ? '保存中...' : '保存到AI复盘' }}
            </button>
            <button
              class="btn btn-success"
              :disabled="saving !== null"
              @click="saveToModule(11, '操作建议')"
            >
              {{ saving === 11 ? '保存中...' : '保存到操作建议' }}
            </button>
          </div>
        </section>
      </template>

      <!-- 未知状态 -->
      <div v-else class="card">
        <div class="analysis-warning">未知分析状态：{{ analysis.status }}</div>
        <button class="btn btn-secondary mt-4" @click="goBack">返回</button>
      </div>
    </template>

    <div v-else class="empty-state">未找到分析记录</div>
  </div>
</template>

<script setup>
import { ref, inject, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { analysisApi } from '../api'

const router = useRouter()
const route = useRoute()
const showToast = inject('toast')

const MODULE_NAMES = [
  '一周策略', '股票1', '股票2', '股票3', '股票4',
  '技术派观点', '钱说观点', '大盘走势', '反向操作',
  'AI复盘', '行业板块', '操作建议',
]

const SECTION_KEYS = [
  '信息汇总', '一致观点', '冲突观点', '关键判断',
  '风险提示', '信息不足之处', '操作参考建议',
]

const id = route.params.id
const analysis = ref(null)
const loading = ref(true)
const parsedResult = ref(null)
const useRaw = ref(false)
const saving = ref(null)
let pollTimer = null

function getModuleName(modId) {
  return MODULE_NAMES[modId] || `模块${modId}`
}

function buildResultText() {
  if (parsedResult.value) {
    return SECTION_KEYS.map((k) => `【${k}】\n${parsedResult.value[k] || ''}`).join('\n\n')
  }
  return analysis.value?.raw_result || ''
}

function parseResult() {
  if (!analysis.value || analysis.value.status !== 'completed') return
  const raw = analysis.value.result_json
  if (!raw) {
    useRaw.value = true
    parsedResult.value = null
    return
  }
  try {
    parsedResult.value = JSON.parse(raw)
    useRaw.value = false
  } catch (e) {
    parsedResult.value = null
    useRaw.value = true
  }
}

async function fetchAnalysis() {
  try {
    const res = await analysisApi.get(id)
    analysis.value = res.data
    parseResult()
    if (analysis.value.status === 'running') {
      startPolling()
    }
  } catch (e) {
    showToast('获取分析结果失败', 'error')
  } finally {
    loading.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await analysisApi.get(id)
      analysis.value = res.data
      if (analysis.value.status === 'completed') {
        stopPolling()
        parseResult()
        showToast('分析已完成', 'success')
      } else if (analysis.value.status === 'failed') {
        stopPolling()
        showToast('分析失败', 'error')
      }
    } catch (e) {
      // 轮询出错时静默，等待下次重试
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function saveToModule(moduleId, label) {
  if (saving.value !== null) return
  saving.value = moduleId
  try {
    const text = buildResultText()
    await analysisApi.saveToModule(id, moduleId, text)
    showToast(`已保存到${label}`, 'success')
  } catch (e) {
    showToast(`保存到${label}失败`, 'error')
  } finally {
    saving.value = null
  }
}

function goBack() {
  router.push('/analysis')
}

function formatTime(t) {
  if (!t) return '-'
  return String(t).replace('T', ' ').slice(0, 19)
}

onMounted(fetchAnalysis)
onUnmounted(stopPolling)
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

.analyzing-loading {
  padding: 80px 20px;
}

.analyzing-text {
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--text);
  margin-top: 16px;
  margin-bottom: 8px;
}

.analyzing-sub {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
}

.info-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
  font-size: var(--font-size-base);
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  flex-shrink: 0;
}

.info-value {
  flex: 1;
  color: var(--text);
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
}

.combo-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.combo-order {
  background: var(--primary);
  color: #fff;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 15px;
}

.combo-name {
  font-weight: 600;
}

.combo-arrow {
  margin: 0 8px;
  color: var(--text-secondary);
  font-size: 18px;
}

.save-buttons {
  flex-wrap: wrap;
}
</style>
